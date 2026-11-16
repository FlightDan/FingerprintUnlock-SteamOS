import asyncio
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch, AsyncMock, MagicMock, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fingerprint_bridge', ROOT / 'bridge/main.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

def root_owned_fixture_stat(path):
    # Preserve real symlink, file-type and mode checks on a non-root test runner.
    info = stat_for_test(path)
    fields = list(info)
    fields[4] = 0
    return os.stat_result(fields)


stat_for_test = Path.lstat


class VerificationTests(unittest.IsolatedAsyncioTestCase):
    async def test_generic_fprintd_profile_needs_no_model_or_sensor_name(self):
        # The service owns device selection; this contract does not attest that
        # any particular driver or multi-sensor configuration is functional.
        for bin_dir in ('/usr/bin', '/var/lib/oxp3-installer/fingerprint/bin'):
            with self.subTest(bin_dir=bin_dir):
                profile = {'verify_command': bin_dir + '/fprintd-verify',
                           'list_command': bin_dir + '/fprintd-list',
                           'enroll_command': bin_dir + '/fprintd-enroll'}
                config_path = Mock()
                config_path.read_text.return_value = json.dumps(profile)
                path_factory = MagicMock()
                path_factory.return_value.parent.__truediv__.return_value = config_path
                plugin = bridge.Plugin()
                with (patch.object(bridge, 'Path', path_factory),
                      patch.dict(bridge.os.environ, {'DECKY_USER': 'deck'}),
                      patch.object(plugin, '_keep_fresh', return_value=None)):
                    await plugin._main()
                self.addAsyncCleanup(plugin._unload)
                async def fake_run(path, timeout, *flags):
                    if path == profile['verify_command']:
                        return 0, 'Verify result: verify-match (done)\n', None
                    if path == profile['list_command']:
                        return 0, '#0: right-index-finger\n', None
                    raise AssertionError('unexpected fprintd command')
                plugin._run = fake_run
                self.assertEqual(await plugin.verify(), {'result': 'match'})
                with patch.object(bridge.os, 'access', return_value=True):
                    self.assertEqual(await plugin.status(), {'available': True, 'enrolled': True,
                                                              'enroll_command': profile['enroll_command'], 'busy': False, 'repairable': False})

    async def test_child_uses_packaged_runpath_without_global_library_override(self):
        plugin = bridge.Plugin()
        plugin.user = 'deck'
        plugin.cancelled = False
        process = AsyncMock()
        process.returncode = 0
        process.communicate.return_value = (b'fixture result', None)
        with patch.object(bridge.asyncio, 'create_subprocess_exec', return_value=process) as spawn:
            self.assertEqual(await plugin._run('/fixture/fprintd-list', 10), (0, 'fixture result', None))
        self.assertEqual(spawn.call_args.args, ('/fixture/fprintd-list', 'deck'))
        with patch.object(bridge.asyncio, 'create_subprocess_exec', return_value=process) as spawn:
            await plugin._run('/fixture/fprintd-verify', 10, '-f', 'any')
        self.assertEqual(spawn.call_args.args, ('/fixture/fprintd-verify', '-f', 'any', 'deck'))
        self.assertEqual(spawn.call_args.kwargs['env'], {'PATH': '/usr/bin:/bin', 'LANG': 'C'})


    async def test_repair_checks_readonly_and_restores_it(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = bridge.Plugin(); plugin.package_lock = asyncio.Lock(); plugin.repairing = False
            plugin.verify_path = '/usr/bin/fprintd-verify'; plugin.cache_root = Path(tmp)
            plugin._prepare_keyring = AsyncMock(return_value=True)
            plugin._saved = Mock(return_value=['/trusted/fprintd', '/trusted/libfprint', '/trusted/libgusb'])
            plugin._strict_config = AsyncMock(return_value='[options]\nLocalFileSigLevel = Required TrustedOnly\n')
            plugin._check_install = AsyncMock(return_value=None)
            calls = []
            async def cmd(timeout, *args):
                calls.append(args)
                if args[:2] == ('steamos-readonly', 'status'): return 0, 'enabled'
                return 0, ''
            plugin._cmd = cmd
            with patch.object(bridge.os, 'access', side_effect=[False, True]):
                self.assertEqual(await plugin.repair(), {'ok': True})
            install = next(c for c in calls if '-U' in c)
            self.assertNotIn('--needed', install)
            self.assertEqual(install[-3:], ('/trusted/fprintd', '/trusted/libfprint', '/trusted/libgusb'))
            self.assertEqual(calls[-2:], [('steamos-readonly', 'enable'), ('steamos-readonly', 'status')])
            async def bad_status(timeout, *args): return 0, 'unknown'
            plugin._cmd = bad_status
            self.assertIn('readonly state', (await plugin.repair())['error'])
            calls.clear()
            async def failed_restore(timeout, *args):
                calls.append(args)
                if args[:2] == ('steamos-readonly', 'status'): return 0, 'enabled'
                if args[:2] == ('steamos-readonly', 'enable'): return 1, 'failed'
                return 0, ''
            plugin._cmd = failed_restore
            with patch.object(bridge.os, 'access', side_effect=[False, True]):
                self.assertIn('restore readonly', (await plugin.repair())['error'])

    async def test_resolved_config_excludes_repositories_and_forces_local_signatures(self):
        plugin = bridge.Plugin()
        plugin._cmd = AsyncMock(return_value=(0, '[options]\nArchitecture = auto\nLocalFileSigLevel = Optional\n[core]\nServer = https://example.invalid\n'))
        config = await plugin._strict_config()
        self.assertIn('Architecture = auto', config)
        self.assertIn('LocalFileSigLevel = Required TrustedOnly', config)
        self.assertNotIn('Optional', config)
        self.assertNotIn('[core]', config)

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership and mode semantics required')
    async def test_keyring_snapshot_cold_warm_and_changed_sources(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sources = root / 'sources'; sources.mkdir()
            for name in bridge.KEYRING_NAMES:
                (sources / name).write_bytes(name.encode())
            plugin = bridge.Plugin(); plugin.cache_root = root
            calls = []
            async def cmd(timeout, *args):
                calls.append((timeout, args))
                if '--populate' in args:
                    build = Path(args[args.index('--gpgdir') + 1])
                    for name in bridge.KEYRING_FILES: (build / name).write_bytes(name.encode())
                    (build / 'private-key').write_bytes(b'not exported')
                return 0, ''
            plugin._cmd = cmd
            with (patch.object(bridge, 'KEYRING_SOURCES', sources),
                  patch.object(Path, 'lstat', root_owned_fixture_stat)):
                for index in range(2):
                    gpg = root / f'operation-{index}'; gpg.mkdir(mode=0o700)
                    self.assertTrue(await plugin._prepare_keyring(gpg))
                    self.assertEqual({p.name for p in gpg.iterdir()}, set(bridge.KEYRING_FILES))
                    for name in bridge.KEYRING_FILES:
                        self.assertEqual((gpg / name).read_bytes(), name.encode())
                    (gpg / 'pubring.gpg').write_bytes(b'operation-local changes')
                self.assertEqual([c[0] for c in calls], [120, 600])
                baseline = next(root.glob('keyring-*'))
                self.assertEqual({p.name for p in baseline.iterdir()}, set(bridge.KEYRING_FILES))
                (sources / bridge.KEYRING_NAMES[-1]).write_bytes(b'changed')
                gpg = root / 'changed'; gpg.mkdir(mode=0o700)
                self.assertTrue(await plugin._prepare_keyring(gpg))
                self.assertEqual(len(calls), 4)
                self.assertEqual(len(list(root.glob('keyring-*'))), 2)

    @unittest.skipIf(os.name == 'nt', 'POSIX ownership and mode semantics required')
    async def test_keyring_failure_and_untrusted_paths_do_not_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); sources = root / 'sources'; sources.mkdir()
            for name in bridge.KEYRING_NAMES:
                (sources / name).write_bytes(b'source')
            plugin = bridge.Plugin(); plugin.cache_root = root
            plugin._cmd = AsyncMock(side_effect=[(0, ''), (1, 'failed')])
            gpg = root / 'operation'; gpg.mkdir(mode=0o700)
            with (patch.object(bridge, 'KEYRING_SOURCES', sources),
                  patch.object(Path, 'lstat', root_owned_fixture_stat)):
                self.assertFalse(await plugin._prepare_keyring(gpg))
                self.assertEqual(list(root.glob('keyring-*')), [])
                generation = plugin._keyring_generation()
                (root / ('keyring-' + generation)).symlink_to(sources, target_is_directory=True)
                plugin._cmd.reset_mock()
                self.assertFalse(await plugin._prepare_keyring(gpg))
                plugin._cmd.assert_not_awaited()
                (sources / bridge.KEYRING_NAMES[0]).unlink()
                (sources / bridge.KEYRING_NAMES[0]).symlink_to(sources / bridge.KEYRING_NAMES[1])
                self.assertFalse(await plugin._prepare_keyring(gpg))

    async def test_status_reports_background_package_lock_when_repair_needed(self):
        plugin = bridge.Plugin(); plugin.lock = asyncio.Lock(); plugin.package_lock = asyncio.Lock()
        plugin.verify_path = '/usr/bin/fprintd-verify'; plugin.list_path = '/usr/bin/fprintd-list'
        plugin.enroll_command = 'enroll'; plugin.repairing = False
        plugin._run = AsyncMock(return_value=(1, '', None))
        async with plugin.package_lock:
            with patch.object(bridge.os, 'access', return_value=False):
                self.assertTrue((await plugin.status())['busy'])

    async def test_offline_repair_refuses_an_installed_dependency_downgrade(self):
        plugin = bridge.Plugin()
        plugin.cache_root = Path(tempfile.gettempdir())
        plugin._strict_config = AsyncMock(return_value='[options]\nLocalFileSigLevel = Required TrustedOnly\n')
        calls = []
        async def cmd(timeout, *args):
            calls.append(args)
            if args[:2] == ('steamos-readonly', 'status'):
                return 0, 'enabled'
            if '--print' in args:
                return 0, 'fprintd\t1-1\nlibfprint\t1-1\nlibgusb\t1-1\n'
            if args[:2] == ('pacman', '-Q'):
                return 1, 'libfprint 2-1\n'
            if args == ('vercmp', '1-1', '2-1'):
                return 0, '-1\n'
            raise AssertionError(args)
        plugin._cmd = cmd
        result = await plugin._install_transaction(['fprintd', 'libfprint', 'libgusb'], '/keys')
        self.assertFalse(result['ok'])
        self.assertIn('older than installed package: libfprint', result['error'])
        self.assertNotIn(('steamos-readonly', 'disable'), calls)

    async def test_retry_download_occurs_after_failed_install(self):
        plugin = bridge.Plugin(); plugin.package_lock = asyncio.Lock()
        plugin._saved = Mock(return_value=['saved'])
        order = []
        async def install(saved):
            order.append('install')
            return {'ok': False, 'error': 'failed', 'retryable': True} if len(order) == 1 else {'ok': True}
        async def download(): order.append('download'); return True
        plugin._install_locked = install; plugin._download_locked = download
        self.assertEqual(await plugin._repair(False), {'ok': True})
        self.assertEqual(order, ['install', 'download', 'install'])

    async def test_alternate_profile_never_repairs(self):
        plugin = bridge.Plugin(); plugin.verify_path = '/custom/verify'
        self.assertEqual((await plugin.repair())['error'], 'unsupported profile')

    async def test_keep_fresh_repairs_missing_fprintd_from_saved_copy_without_network(self):
        plugin = bridge.Plugin(); plugin.verify_path = '/usr/bin/fprintd-verify'
        repairs, downloads = [], []
        async def fake_repair(offline_only=False): repairs.append(offline_only); return {'ok': True}
        async def fake_download(): downloads.append(1); return len(downloads) > 1
        async def fake_seed(): pass
        async def stop(delay):
            if len(downloads) > 1: raise asyncio.CancelledError
        plugin.repair, plugin._download_latest, plugin._seed_cache = fake_repair, fake_download, fake_seed
        with patch.object(bridge.asyncio, 'sleep', stop), self.assertRaises(asyncio.CancelledError):
            await plugin._keep_fresh()
        # once at startup, once when the first successful download arrives; never online
        self.assertEqual(repairs, [True, True])

    async def test_download_publishes_only_complete_authenticated_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            plugin = bridge.Plugin(); plugin.cache_root = Path(tmp); plugin.packages = Path(tmp, 'current')
            plugin.package_lock = asyncio.Lock(); plugin._cache_ready = Mock(return_value=True)
            plugin._saved = Mock(return_value=['complete'])
            plugin._authenticate = AsyncMock(return_value=True)
            plugin._prepare_keyring = AsyncMock(return_value=True)
            real_lstat = Path.lstat
            def lstat(path, *args, **kwargs):
                if path == Path(tmp): return Mock(st_mode=0o41777, st_uid=0)
                return real_lstat(path, *args, **kwargs)
            calls = []
            names = ['fprintd', 'libfprint', 'libgusb']
            async def cmd(timeout, *args):
                calls.append(args)
                if '-Sp' in args:
                    return 0, ''.join(f'{n}\t{n}-1-1-x86_64.pkg.tar.zst\t1-1\tc2ln\n' for n in names)
                if '-Sw' in args:
                    stage = Path(args[args.index('--cachedir') + 1])
                    for n in names: (stage / f'{n}-1-1-x86_64.pkg.tar.zst').write_bytes(b'package')
                    (stage / 'dependency-1-1-x86_64.pkg.tar.zst').write_bytes(b'extra')
                return 0, ''
            plugin._cmd = cmd
            published = []
            plugin._publish = Mock(side_effect=lambda stage: published.append(sorted(p.name for p in stage.iterdir())))
            with patch.object(bridge, 'TEMP_ROOT', Path(tmp)), patch.object(Path, 'lstat', lstat):
                self.assertTrue(await plugin._download_latest())
            self.assertEqual(len(published[0]), 6)
            download = next(c for c in calls if '-Sw' in c)
            self.assertEqual(download[-3:], tuple(names))
            plugin._authenticate.return_value = False
            with patch.object(bridge, 'TEMP_ROOT', Path(tmp)), patch.object(Path, 'lstat', lstat):
                self.assertFalse(await plugin._download_latest())
            self.assertEqual(len(published), 1)

    async def test_command_timeout_terminates_and_drains_process_group(self):
        plugin = bridge.Plugin()
        finished = asyncio.Event()
        proc = AsyncMock(pid=123)
        async def communicate():
            await finished.wait()
            return b'', None
        proc.communicate.side_effect = communicate
        with (patch.object(bridge.asyncio, 'create_subprocess_exec', return_value=proc) as spawn,
              patch.object(bridge.signal, 'SIGKILL', 9, create=True),
              patch.object(bridge.os, 'killpg', side_effect=lambda *args: finished.set(), create=True) as kill):
            result = await plugin._cmd(0.001, 'fixture')
        self.assertEqual(result, (None, 'timeout'))
        self.assertTrue(spawn.call_args.kwargs['start_new_session'])
        kill.assert_called_once_with(proc.pid, bridge.signal.SIGTERM)
        proc.communicate.assert_awaited_once()

    async def test_unload_without_repair_waits_for_background_cleanup(self):
        plugin = bridge.Plugin()
        started, cleaned = asyncio.Event(), asyncio.Event()
        async def background():
            try:
                started.set()
                await asyncio.sleep(60)
            finally:
                await asyncio.sleep(0)
                cleaned.set()
        profile = {'verify_command': '/usr/bin/fprintd-verify',
                   'list_command': '/usr/bin/fprintd-list',
                   'enroll_command': '/usr/bin/fprintd-enroll'}
        with (patch.object(Path, 'read_text', return_value=json.dumps(profile)),
              patch.object(plugin, '_keep_fresh', side_effect=background)):
            await plugin._main()
        await started.wait()
        await plugin._unload()
        self.assertTrue(cleaned.is_set())
        self.assertTrue(plugin.fresh_task.cancelled())

    async def test_failure_cancel_and_partial_match_cannot_unlock(self):
        plugin = bridge.Plugin()
        plugin.lock = asyncio.Lock()
        plugin.verify_path = '/nonexistent'
        for code, output, cancelled in [(1, 'Verify result: verify-match (done)', False),
                (0, 'verify-match', False), (None, '', False),
                (0, 'Verify result: verify-no-match (done)\nVerify result: verify-match (done)', False),
                (0, 'Verify result: verify-match (done)', True)]:
            async def fake_run(path, timeout, *flags):
                plugin.cancelled = cancelled
                return code, output, None
            plugin._run = fake_run
            self.assertNotEqual((await plugin.verify())['result'], 'match')
        async def success(path, timeout, *flags):
            return 0, 'Verify result: verify-match (done)\n', None
        plugin._run = success
        self.assertEqual((await plugin.verify())['result'], 'match')


    async def test_retry_reasons_are_explicit_and_fail_closed(self):
        plugin = bridge.Plugin(); plugin.lock = asyncio.Lock(); plugin.verify_path = 'fixture'
        for code, output, reason, expected in [
            (None, '', 'timeout', 'timeout'),
            (1, 'Verify result: verify-unknown-error (done)\n', None, 'device-error'),
            (0, 'Verify result: verify-unknown-error (done)\n', None, 'error'),
            (1, 'Verify result: verify-unknown-error (not done)\n', None, 'error'),
            (1, 'Verify result: verify-disconnected (done)\n', None, 'error'),
            (1, 'VerifyStart failed: fixture\n', None, 'error'),
            (1, 'Verify result: verify-unknown-error (done)\nVerifyStop failed: fixture\n', None, 'error'),
            (1, 'Verify result: verify-unknown-error (done)\nVerify result: verify-match (done)\n', None, 'error'),
            (1, 'Verify result: verify-unknown-error (done)\nVerify result: verify-unknown-error (done)\n', None, 'error'),
            (1, 'Verify result: verify-unknown-error (done)\n', 'cancelled', 'cancelled'),
            (1, 'Verify result: verify-no-match (done)\n', None, 'no-match'),
            (0, 'Verify result: verify-no-match (done)\n', None, 'error'),
            (1, 'Verify result: verify-match (done)\n', None, 'error'),
            (1, 'Verify result: verify-no-match (done)\nVerify result: verify-no-match (done)\n', None, 'error'),
        ]:
            async def fake_run(path, timeout, *flags): return code, output, reason
            plugin._run = fake_run
            self.assertEqual(await plugin.verify(), {'result': 'unavailable', 'reason': expected})


    async def test_cancel_during_startup_reaps_child(self):
        plugin = bridge.Plugin(); plugin.lock = asyncio.Lock(); plugin.verify_path = 'fixture'; plugin.user = 'deck'; plugin.proc = None
        started = asyncio.Event(); resume = asyncio.Event()
        proc = AsyncMock(); proc.returncode = -9; proc.terminate = Mock(); proc.kill = Mock()
        async def spawn(*args, **kwargs):
            started.set(); await resume.wait(); return proc
        with patch.object(bridge.asyncio, 'create_subprocess_exec', side_effect=spawn):
            task = asyncio.create_task(plugin.verify()); await started.wait()
            await plugin.cancel(); resume.set()
            self.assertEqual(await task, {'result': 'unavailable', 'reason': 'cancelled'})
        proc.terminate.assert_called_once(); proc.wait.assert_awaited()


    async def test_termination_escalates_when_child_ignores_term(self):
        plugin = bridge.Plugin()
        proc = AsyncMock(); proc.terminate = Mock(); proc.kill = Mock()
        proc.wait.side_effect = [asyncio.TimeoutError(), None]
        await plugin._stop(proc)
        proc.terminate.assert_called_once(); proc.kill.assert_called_once()
        self.assertEqual(proc.wait.await_count, 2)


