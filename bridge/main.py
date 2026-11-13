"""Fingerprint verification bridge; PIN and template bytes are never handled here."""
import asyncio
import json
import os
from pathlib import Path
import re
import shutil

PACKAGES = ('fprintd', 'libfprint', 'libgusb')
PACMAN_CACHE = Path('/var/cache/pacman/pkg')


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
        self.packages = Path(os.environ.get('DECKY_PLUGIN_RUNTIME_DIR') or Path(__file__).parent) / 'packages'
        self.fresh_task = asyncio.create_task(self._keep_fresh())

    async def _stop(self, proc):
        try:
            proc.terminate()
        except ProcessLookupError:
            return
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
            self.proc = await asyncio.create_subprocess_exec(
                executable, *flags, self.user, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT, env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            if self.cancelled:
                await self._stop(self.proc)
                return None, '', 'cancelled'
            try:
                output, _ = await asyncio.wait_for(self.proc.communicate(), timeout)
            except asyncio.TimeoutError:
                await self._stop(self.proc)
                return None, '', 'timeout'
            return self.proc.returncode, output.decode('utf-8', errors='replace'), None
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
            return {'available': False}
        async with self.lock:
            self.cancelled = False
            code, text, _ = await self._run(self.list_path, 10)
            return {'available': code == 0, 'enrolled': bool(re.search(r'#\d+:\s*\S+', text)) if code == 0 else False,
                    'enroll_command': self.enroll_command}

    async def _cmd(self, timeout, *args):
        try:
            proc = await asyncio.create_subprocess_exec(
                *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
                env={'PATH': '/usr/bin:/bin', 'LANG': 'C'})
            out, _ = await asyncio.wait_for(proc.communicate(), timeout)
            return proc.returncode, out.decode('utf-8', errors='replace')
        except (OSError, asyncio.TimeoutError) as exc:
            return None, str(exc)

    async def _keep_fresh(self):
        """Keep the saved packages current and restore fprintd after a SteamOS update removed it."""
        def missing():
            return not os.access(self.verify_path, os.X_OK)
        await self._seed_cache()
        if missing():
            await self.repair(offline_only=True)
        while True:
            fetched = await self._download_latest()
            if fetched and missing():
                await self.repair(offline_only=True)
            await asyncio.sleep(12 * 3600 if fetched else 600)

    async def _seed_cache(self):
        """First run, possibly offline: copy the installed versions from pacman's own cache."""
        code, out = await self._cmd(10, 'pacman', '-Q', *PACKAGES)
        installed = [line.split() for line in out.splitlines()] if code == 0 else []
        try:
            self.packages.mkdir(parents=True, exist_ok=True)
            for name, version in installed:
                if next(self.packages.glob(f'{name}-[0-9]*.pkg.tar.*'), None) is None:
                    for source in PACMAN_CACHE.glob(f'{name}-{version}-*.pkg.tar.*'):
                        shutil.copy2(source, self.packages / source.name)
        except OSError:
            pass

    async def _download_latest(self):
        """Fetch the newest signed packages with a private sync database: no network means False, the system database and read-only root stay untouched."""
        code, dbpath = await self._cmd(10, 'pacman-conf', 'DBPath')
        if code != 0:
            return False
        db = self.packages.with_name('db')
        try:
            (db / 'sync').mkdir(parents=True, exist_ok=True)
            self.packages.mkdir(parents=True, exist_ok=True)
            (db / 'local').unlink(missing_ok=True)
            (db / 'local').symlink_to(Path(dbpath.strip()) / 'local')
        except OSError:
            return False
        base = ('pacman', '--dbpath', str(db), '--cachedir', str(self.packages))
        if (await self._cmd(120, *base, '-Sy', '--noconfirm'))[0] != 0:
            return False
        code, info = await self._cmd(30, *base, '-Si', *PACKAGES)
        if code != 0 or (await self._cmd(300, *base, '-Sw', '--noconfirm', *PACKAGES))[0] != 0:
            return False
        versions = zip(re.findall(r'^Name\s*: (\S+)', info, re.M), re.findall(r'^Version\s*: (\S+)', info, re.M))
        for name, version in versions:
            for stale in self.packages.glob(f'{name}-[0-9]*.pkg.tar.*'):
                if not stale.name.startswith(f'{name}-{version}-'):
                    stale.unlink()
        return True

    def _saved(self):
        return sorted(str(f) for f in self.packages.glob('*.pkg.tar.*') if f.suffix != '.sig')

    async def repair(self, offline_only=False):
        """Reinstall fprintd/libfprint after a SteamOS update wipes them (runs as root)."""
        saved = self._saved()
        if self.lock.locked():
            return {'ok': False, 'error': 'busy'}
        if offline_only and not saved:
            return {'ok': False, 'error': 'no saved packages'}
        async with self.lock:
            _, state = await self._cmd(10, 'steamos-readonly', 'status')
            was_readonly = state.strip() == 'enabled'
            try:
                if (await self._cmd(30, 'steamos-readonly', 'disable'))[0] != 0:
                    return {'ok': False, 'error': 'cannot unlock the system partition'}
                await self._cmd(120, 'pacman-key', '--init')
                await self._cmd(120, 'pacman-key', '--populate', 'archlinux', 'holo')
                # The saved copy works offline, so it goes first.
                code, out = await self._cmd(120, 'pacman', '-U', '--needed', '--noconfirm', *saved) if saved else (None, 'no saved packages')
                if (code != 0 or not os.access(self.verify_path, os.X_OK)) and not offline_only and await self._download_latest():
                    code, out = await self._cmd(120, 'pacman', '-U', '--needed', '--noconfirm', *self._saved())
            finally:
                if was_readonly:
                    await self._cmd(30, 'steamos-readonly', 'enable')
            if code != 0 or not os.access(self.verify_path, os.X_OK):
                return {'ok': False, 'error': out[-300:]}
            return {'ok': True}

    async def _unload(self):
        self.fresh_task.cancel()
        await self.cancel()
