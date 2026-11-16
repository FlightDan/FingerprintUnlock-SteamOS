"""Fingerprint verification bridge; PIN and template bytes are never handled here."""
import asyncio
import base64
import contextlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import tempfile

PACKAGES = ('fprintd', 'libfprint', 'libgusb')
PACMAN_CACHE = Path('/var/cache/pacman/pkg')
CACHE_ROOT = Path('/home/.boiler-fingerprint')
TEMP_ROOT = Path('/tmp')


class Plugin:
    async def _main(self):
        config = json.loads((Path(__file__).parent / 'profile.json').read_text())
        self.verify_path = config['verify_command']
        self.list_path = config['list_command']
        self.enroll_command = config['enroll_command']
        self.user = os.environ.get('DECKY_USER', 'deck')
        self.lock = asyncio.Lock()
        self.proc = None
        self.cancelled = False
        self.package_lock = asyncio.Lock()
        self.repairing = False
        self.repair_task = None
        self.cache_root = CACHE_ROOT
        self.packages = self.cache_root / 'current'
        self.fresh_task = asyncio.create_task(self._keep_fresh())

    async def _stop(self, proc):
        try:
            proc.terminate()
        except ProcessLookupError:
            pass
        try:
            await asyncio.wait_for(proc.wait(), 3)
        except asyncio.TimeoutError:
            try:
                proc.kill()
            except ProcessLookupError:
                return
            try:
                await asyncio.wait_for(proc.wait(), 3)
            except asyncio.TimeoutError:
                pass

    async def _run(self, executable, timeout, *flags):
        try:
            spawn = asyncio.create_task(asyncio.create_subprocess_exec(
                executable, *flags, self.user, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'}))
            try:
                self.proc = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                self.proc = await spawn
                raise
            if self.cancelled:
                await self._stop(self.proc)
                return None, '', 'cancelled'
            try:
                output, _ = await asyncio.wait_for(self.proc.communicate(), timeout)
            except asyncio.TimeoutError:
                await self._stop(self.proc)
                return None, '', 'timeout'
            return self.proc.returncode, output.decode('utf-8', errors='replace'), None
        except asyncio.CancelledError:
            if self.proc is not None:
                await asyncio.shield(self._stop(self.proc))
            raise
        except (OSError, ProcessLookupError):
            return None, '', 'error'
        finally:
            self.proc = None

    async def verify(self, timeout_s=30):
        if self.lock.locked():
            return {'result': 'busy'}
        async with self.lock:
            self.cancelled = False
            # fprintd-verify without -f tries only the first enrolled finger; 'any' matches all of them.
            code, text, reason = await self._run(self.verify_path, max(1, min(int(timeout_s), 30)), '-f', 'any')
            # Exact result line and successful process completion are both required.
            results = re.findall(r'^Verify result: ([^\r\n]+)[ \t]*$', text, re.M)
            if self.cancelled:
                return {'result': 'unavailable', 'reason': 'cancelled'}
            if code == 0 and len(results) == 1 and results[0].strip() == 'verify-match (done)':
                return {'result': 'match'}
            if code == 1 and len(results) == 1 and results[0].strip() == 'verify-no-match (done)':
                reason = 'no-match'
            elif (reason is None and code == 1 and len(results) == 1
                  and results[0].strip() == 'verify-unknown-error (done)'
                  and not re.search(r'^(?:VerifyStart|VerifyStop) failed:', text, re.M)):
                reason = 'device-error'
            return {'result': 'unavailable', 'reason': reason or 'error'}

    async def cancel(self):
        self.cancelled = True
        proc = self.proc
        if proc is not None:
            await self._stop(proc)
        return {'cancelled': True}

    async def status(self):
        if self.lock.locked():
            return {'available': False, 'busy': True, 'repairable': self.verify_path == '/usr/bin/fprintd-verify'}
        async with self.lock:
            self.cancelled = False
            code, text, _ = await self._run(self.list_path, 10)
            return {'available': code == 0, 'enrolled': bool(re.search(r'#\d+:\s*\S+', text)) if code == 0 else False,
                    'enroll_command': self.enroll_command, 'busy': self.repairing,
                    'repairable': self.verify_path == '/usr/bin/fprintd-verify' and not os.access(self.verify_path, os.X_OK)}

    async def _stop_command(self, proc, completion):
        for sig in (signal.SIGTERM, signal.SIGKILL):
            with contextlib.suppress(ProcessLookupError):
                os.killpg(proc.pid, sig)
            try:
                await asyncio.wait_for(asyncio.shield(completion), 1)
                return
            except asyncio.TimeoutError:
                continue
        logging.error('fingerprint package command did not stop')

    async def _cmd(self, timeout, *args):
        spawn = asyncio.create_task(asyncio.create_subprocess_exec(
            *args, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, start_new_session=True,
            env={'PATH': '/usr/bin:/bin', 'LANG': 'C'}))
        try:
            try:
                proc = await asyncio.shield(spawn)
            except asyncio.CancelledError:
                proc = await spawn
                await self._stop_command(proc, asyncio.create_task(proc.communicate()))
                raise
            completion = asyncio.create_task(proc.communicate())
            try:
                out, _ = await asyncio.wait_for(asyncio.shield(completion), timeout)
            except asyncio.TimeoutError:
                await self._stop_command(proc, completion)
                return None, 'timeout'
            except asyncio.CancelledError:
                await self._stop_command(proc, completion)
                raise
            return proc.returncode, out.decode('utf-8', errors='replace')
        except OSError as exc:
            return None, str(exc)

    def _cache_ready(self):
        """Only use the fixed private cache when its entire ancestry is trusted."""
        try:
            for path in reversed(self.cache_root.parents):
                st = path.lstat()
                if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
                    return False
            try:
                self.cache_root.mkdir(mode=0o700)
            except FileExistsError:
                pass
            st = self.cache_root.lstat()
            return stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700
        except OSError:
            return False

    def _publish(self, stage):
        previous = None
        if self.packages.is_symlink():
            name = os.readlink(self.packages)
            if re.fullmatch(r'set-[a-z0-9_]+', name):
                candidate = self.cache_root / name
                st = candidate.lstat()
                if stat.S_ISDIR(st.st_mode) and st.st_uid == 0 and not st.st_mode & 0o022:
                    previous = candidate
        target = self.cache_root / ('set-' + next(tempfile._get_candidate_names()))
        stage.rename(target)
        link = self.cache_root / ('link-' + next(tempfile._get_candidate_names()))
        switched = False
        try:
            link.symlink_to(target.name, target_is_directory=True)
            os.replace(link, self.packages)
            switched = True
        finally:
            link.unlink(missing_ok=True)
            if not switched:
                shutil.rmtree(target)
        if previous is not None:
            shutil.rmtree(previous)

    def _saved(self):
        if not self._cache_ready():
            return []
        try:
            if not self.packages.is_symlink():
                return []
            target = os.readlink(self.packages)
            if not re.fullmatch(r'set-[a-z0-9_]+', target):
                return []
            directory = self.cache_root / target
            st = directory.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022:
                return []
            files = list(directory.iterdir())
            result = []
            for name in PACKAGES:
                matches = [p for p in files if re.fullmatch(re.escape(name) + r'-[0-9][^/]*\.pkg\.tar\.(?:zst|xz|gz)', p.name)]
                if len(matches) != 1:
                    return []
                package = matches[0]
                for path in (package, package.with_name(package.name + '.sig')):
                    st = path.lstat()
                    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or st.st_mode & 0o022 or st.st_size == 0:
                        return []
                result.append(str(package))
            return result
        except OSError:
            return []

    async def _keep_fresh(self):
        if self.verify_path != '/usr/bin/fprintd-verify':
            return
        def missing():
            return not os.access(self.verify_path, os.X_OK)
        await self._seed_cache()
        if missing():
            result = await self.repair(offline_only=True)
            if not result['ok']: logging.error('fingerprint restore failed: %s', result['error'])
        while True:
            fetched = await self._download_latest()
            if fetched and missing():
                result = await self.repair(offline_only=True)
                if not result['ok']: logging.error('fingerprint restore failed: %s', result['error'])
            await asyncio.sleep(12 * 3600 if fetched else 600)

    async def _seed_cache(self):
        async with self.package_lock:
            if not self._cache_ready() or self._saved():
                return False
            code, out = await self._cmd(10, 'pacman', '-Q', *PACKAGES)
            rows = [line.split() for line in out.splitlines()]
            if code != 0 or len(rows) != len(PACKAGES) or {r[0] for r in rows if len(r) == 2} != set(PACKAGES):
                return False
            with tempfile.TemporaryDirectory(dir=self.cache_root, prefix='stage-') as tmp:
                stage = Path(tmp)
                try:
                    copied = []
                    for name, version in rows:
                        matches = [p for p in PACMAN_CACHE.glob(f'{name}-{version}-*.pkg.tar.*') if not p.name.endswith('.sig')]
                        if len(matches) != 1 or not matches[0].with_name(matches[0].name + '.sig').is_file():
                            return False
                        copied.append((name, version, matches[0].name))
                        for source in (matches[0], matches[0].with_name(matches[0].name + '.sig')):
                            shutil.copyfile(source, stage / source.name)
                    metadata = [[name, matches_name, version, ''] for name, version, matches_name in copied]
                    with tempfile.TemporaryDirectory(dir=self.cache_root, prefix='keys-') as keys:
                        gpg = Path(keys) / 'gnupg'; gpg.mkdir(mode=0o700)
                        if not await self._prepare_keyring(gpg) or not await self._authenticate(stage, metadata, gpg):
                            return False
                    self._publish(stage)
                    return bool(self._saved())
                except (OSError, ValueError):
                    return False

    async def _download_latest(self):
        async with self.package_lock:
            return await self._download_locked()

    async def _download_locked(self):
        if not self._cache_ready():
            return False
        try:
            temp_root = TEMP_ROOT
            st = temp_root.lstat()
            if not stat.S_ISDIR(st.st_mode) or st.st_uid != 0 or not st.st_mode & stat.S_ISVTX:
                return False
            with tempfile.TemporaryDirectory(dir=temp_root, prefix='boiler-fprint-') as tmp, tempfile.TemporaryDirectory(dir=self.cache_root, prefix='fetch-') as private:
                root = Path(tmp); root.chmod(0o711)
                db = root / 'db'; stage = root / 'packages'; gpg = Path(private) / 'gnupg'
                (db / 'sync').mkdir(parents=True); stage.mkdir(); gpg.mkdir(mode=0o700)
                if not await self._prepare_keyring(gpg):
                    return False
                base = ('pacman', '--dbpath', str(db), '--cachedir', str(stage),
                        '--gpgdir', str(gpg), '--logfile', str(Path(private) / 'pacman.log'))
                if (await self._cmd(120, *base, '-Sy', '--noconfirm'))[0] != 0:
                    return False
                code, metadata = await self._cmd(30, *base, '-Sp', '--nodeps', '--print-format', '%n\t%f\t%v\t%g', *PACKAGES)
                if code != 0:
                    return False
                rows = [line.split('\t') for line in metadata.splitlines()]
                if len(rows) != len(PACKAGES) or any(len(r) != 4 for r in rows) or {r[0] for r in rows} != set(PACKAGES):
                    return False
                for name, filename, version, signature in rows:
                    if not re.fullmatch(re.escape(name) + r'-[0-9][^/]*\.pkg\.tar\.(?:zst|xz|gz)', filename) or not version:
                        return False
                if (await self._cmd(300, *base, '-Sw', '--nodeps', '--noconfirm', *PACKAGES))[0] != 0:
                    return False
                for name, filename, version, signature in rows:
                    package = stage / filename; sig = stage / (filename + '.sig')
                    if not package.is_file() or package.stat().st_size == 0:
                        return False
                    if not sig.is_file() and signature and signature != '(null)':
                        sig.write_bytes(base64.b64decode(signature, validate=True))
                    if not sig.is_file() or sig.stat().st_size == 0:
                        return False
                keep = {r[1] for r in rows} | {r[1] + '.sig' for r in rows}
                protected = Path(private) / 'packages'; protected.mkdir()
                for filename in keep:
                    source = stage / filename
                    st = source.lstat()
                    if not stat.S_ISREG(st.st_mode) or st.st_uid != 0:
                        return False
                    shutil.copyfile(source, protected / filename)
                if not await self._authenticate(protected, rows, gpg):
                    return False
                self._publish(protected)
                return bool(self._saved())
        except (OSError, ValueError):
            return False

    async def _authenticate(self, stage, rows, gpg=None):
        config_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.cache_root, prefix='pacman-', delete=False) as f:
                config_path = f.name
                f.write(await self._strict_config())
            paths = [str(stage / row[1]) for row in rows]
            key_args = ('--gpgdir', str(gpg)) if gpg else ()
            code, out = await self._cmd(120, 'pacman', '--config', config_path, *key_args, '-U', '--print',
                                        '--print-format', '%n\t%v', *paths)
            expected = {(r[0], r[2]) for r in rows}
            found = {tuple(line.split('\t')) for line in out.splitlines()}
            return code == 0 and {row for row in found if len(row) == 2} == expected
        finally:
            if config_path:
                Path(config_path).unlink(missing_ok=True)

    async def _strict_config(self):
        code, text = await self._cmd(10, 'pacman-conf')
        if code != 0:
            raise ValueError('cannot resolve pacman configuration')
        match = re.search(r'^\s*\[options\]\s*$', text, re.M | re.I)
        if not match:
            raise ValueError('missing pacman options')
        end = re.search(r'^\s*\[', text[match.end():], re.M)
        pos = match.end() + end.start() if end else len(text)
        options = re.sub(r'^\s*LocalFileSigLevel\s*=.*$', '', text[match.end():pos], flags=re.M | re.I)
        return '[options]\n' + options + '\nLocalFileSigLevel = Required TrustedOnly\n'

    async def repair(self, offline_only=False):
        if self.verify_path != '/usr/bin/fprintd-verify':
            return {'ok': False, 'error': 'unsupported profile'}
        if os.access(self.verify_path, os.X_OK):
            return {'ok': False, 'error': 'fingerprint service is already installed'}
        if self.package_lock.locked():
            return {'ok': False, 'error': 'busy'}
        self.repairing = True
        self.repair_task = asyncio.current_task()
        try:
            return await self._repair(offline_only)
        finally:
            self.repairing = False
            self.repair_task = None

    async def _repair(self, offline_only):
        async with self.package_lock:
            saved = self._saved()
            if not saved and not offline_only:
                await self._download_locked()
                saved = self._saved()
            if not saved:
                return {'ok': False, 'error': 'no saved packages'}
            result = await self._install_locked(saved)
            if not result['ok'] and not offline_only and result.get('retryable'):
                if await self._download_locked():
                    result = await self._install_locked(self._saved())
            result.pop('retryable', None)
            return result

    async def _prepare_keyring(self, gpg):
        for args in (('pacman-key', '--gpgdir', str(gpg), '--init'),
                     ('pacman-key', '--gpgdir', str(gpg), '--populate', 'archlinux', 'holo')):
            code, out = await self._cmd(120, *args)
            if code != 0:
                logging.error('cannot prepare fingerprint keyring: %s', out[-300:])
                return False
        return True

    async def _install_locked(self, saved):
        with tempfile.TemporaryDirectory(dir=self.cache_root, prefix='install-') as tmp:
            gpg = Path(tmp) / 'gnupg'; gpg.mkdir(mode=0o700)
            if not await self._prepare_keyring(gpg):
                return {'ok': False, 'error': 'cannot prepare trusted keyring'}
            return await self._install_transaction(saved, gpg)

    async def _check_install(self, command, saved):
        code, output = await self._cmd(120, *command, '--print', '--print-format', '%n\t%v', *saved)
        planned = [line.split('\t') for line in output.splitlines() if '\t' in line]
        if code != 0 or len(planned) != len(PACKAGES) or any(len(row) != 2 for row in planned):
            return 'cannot verify cached package transaction: ' + output[-250:]
        versions = dict(planned)
        if set(versions) != set(PACKAGES):
            return 'cached package transaction has unexpected targets'

        code, output = await self._cmd(10, 'pacman', '-Q', *PACKAGES)
        if code not in (0, 1):
            return 'cannot read installed package versions'
        for line in output.splitlines():
            fields = line.split()
            if len(fields) != 2 or fields[0] not in versions:
                continue
            name, installed = fields
            code, comparison = await self._cmd(10, 'vercmp', versions[name], installed)
            if code != 0:
                return 'cannot compare installed package version: ' + name
            try:
                if int(comparison) < 0:
                    return 'cached package is older than installed package: ' + name
            except ValueError:
                return 'cannot compare installed package version: ' + name
        return None

    async def _install_transaction(self, saved, gpg):
        try:
            config = await self._strict_config()
            with tempfile.NamedTemporaryFile(mode='w', dir=self.cache_root, prefix='pacman-', delete=False) as f:
                f.write(config); config_path = f.name
        except (OSError, ValueError) as exc:
            return {'ok': False, 'error': str(exc)}
        try:
            code, state = await self._cmd(10, 'steamos-readonly', 'status')
            status = state.strip()
            was_readonly = code == 0 and status == 'enabled'
            disabled = code == 1 and status in ('disabled', 'disabled, but loaded sysexts may result in some parts of the filesystem being read-only')
            if not (was_readonly or disabled):
                return {'ok': False, 'error': 'cannot determine readonly state'}
            command = ('pacman', '--config', config_path, '--gpgdir', str(gpg), '-U', '--noconfirm')
            error = await self._check_install(command, saved)
            if error:
                return {'ok': False, 'error': error, 'retryable': True}
            result = {'ok': False, 'error': 'installation failed'}
            try:
                if was_readonly and (await self._cmd(30, 'steamos-readonly', 'disable'))[0] != 0:
                    result = {'ok': False, 'error': 'cannot unlock the system partition'}
                else:
                    code, out = await self._cmd(120, *command, *saved)
                    result = {'ok': True} if code == 0 and os.access(self.verify_path, os.X_OK) else {'ok': False, 'error': out[-300:], 'retryable': True}
            finally:
                if was_readonly:
                    restore, _ = await asyncio.shield(self._cmd(30, 'steamos-readonly', 'enable'))
                    check, state = await asyncio.shield(self._cmd(10, 'steamos-readonly', 'status'))
                    if restore != 0 or check != 0 or state.strip() != 'enabled':
                        result = {'ok': False, 'error': 'failed to restore readonly state'}
            return result
        finally:
            Path(config_path).unlink(missing_ok=True)

    async def _unload(self):
        self.fresh_task.cancel()
        await self.cancel()
        repair_task = self.repair_task
        if repair_task is not None and repair_task is not self.fresh_task:
            repair_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self.fresh_task
        if repair_task is not None and repair_task is not self.fresh_task:
            with contextlib.suppress(asyncio.CancelledError):
                await repair_task
