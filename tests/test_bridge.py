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
                with patch.object(bridge, 'Path', path_factory), patch.dict(bridge.os.environ, {'DECKY_USER': 'deck'}):
                    await plugin._main()
                async def fake_run(path, timeout, *flags):
                    if path == profile['verify_command']:
                        return 0, 'Verify result: verify-match (done)\n', None
                    if path == profile['list_command']:
                        return 0, '#0: right-index-finger\n', None
                    raise AssertionError('unexpected fprintd command')
                plugin._run = fake_run
                self.assertEqual(await plugin.verify(), {'result': 'match'})
                self.assertEqual(await plugin.status(), {'available': True, 'enrolled': True,
                                                          'enroll_command': profile['enroll_command']})

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


    async def test_repair_prefers_saved_packages_then_downloads_and_restores_readonly(self):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, 'fprintd-1-1-x86_64.pkg.tar.zst').touch()
            Path(tmp, 'fprintd-1-1-x86_64.pkg.tar.zst.sig').touch()
            # (saved copy present, offline install code, download ok, final install code) -> (ok, pacman -U calls, downloads)
            for saved, offline, fetched, final, ok, installs, downloads in [
                    (True, 0, False, 0, True, 1, 0), (True, 1, True, 0, True, 2, 1),
                    (False, 0, True, 0, True, 1, 1), (True, 1, False, 0, False, 1, 1), (True, 1, True, 1, False, 2, 1)]:
                plugin = bridge.Plugin(); plugin.lock = asyncio.Lock(); plugin.verify_path = '/usr/bin/true'
                plugin.packages = Path(tmp) if saved else Path(tmp, 'none')
                calls = []; results = iter([offline, final] if saved else [final])
                async def fake_cmd(timeout, *args):
                    calls.append(args)
                    if args[:2] == ('steamos-readonly', 'status'):
                        return 0, 'enabled\n'
                    return (next(results), 'boom') if args[:2] == ('pacman', '-U') else (0, '')
                async def fake_download(): downloads_made.append(1); return fetched
                downloads_made = []
                plugin._cmd, plugin._download_latest = fake_cmd, fake_download
                self.assertEqual((await plugin.repair())['ok'], ok)
                self.assertEqual(len([c for c in calls if c[:2] == ('pacman', '-U')]), installs)
                self.assertEqual(len(downloads_made), downloads)
                self.assertEqual(calls[1], ('steamos-readonly', 'disable'))
                self.assertEqual(calls[-1], ('steamos-readonly', 'enable'))
                if saved:
                    pkg = next(c for c in calls if c[:2] == ('pacman', '-U'))
                    self.assertEqual([a for a in pkg if 'pkg.tar' in a], [str(Path(tmp, 'fprintd-1-1-x86_64.pkg.tar.zst'))])

    async def test_keep_fresh_repairs_missing_fprintd_from_saved_copy_without_network(self):
        plugin = bridge.Plugin(); plugin.verify_path = '/nonexistent/fprintd-verify'
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

    async def test_download_latest_uses_private_database_and_prunes_old_versions(self):
        with tempfile.TemporaryDirectory() as tmp:
            packages = Path(tmp, 'packages'); packages.mkdir()
            for name in ('fprintd-1-1-x86_64.pkg.tar.zst', 'fprintd-2-1-x86_64.pkg.tar.zst', 'libfprint-9-1-x86_64.pkg.tar.zst'):
                Path(packages, name).touch()
            plugin = bridge.Plugin(); plugin.packages = packages
            calls = []
            async def fake_cmd(timeout, *args):
                calls.append(args)
                if args[0] == 'pacman-conf': return 0, '/system/db/\n'
                if '-Si' in args: return 0, 'Name : fprintd\nVersion : 2-1\nName : libfprint\nVersion : 9-1\n'
                return 0, ''
            plugin._cmd = fake_cmd
            self.assertTrue(await plugin._download_latest())
            self.assertEqual(sorted(p.name for p in packages.iterdir()),
                             ['fprintd-2-1-x86_64.pkg.tar.zst', 'libfprint-9-1-x86_64.pkg.tar.zst'])
            self.assertEqual(os.readlink(Path(tmp, 'db', 'local')), '/system/db/local')
            self.assertTrue(all(c[1:3] == ('--dbpath', str(Path(tmp, 'db'))) for c in calls if c[0] == 'pacman'))
            self.assertTrue(all('steamos-readonly' not in c for c in calls))
            async def offline(timeout, *args): return (1, '') if '-Sy' in args else (0, '/system/db\n')
            plugin._cmd = offline
            Path(packages, 'fprintd-1-1-x86_64.pkg.tar.zst').touch()
            self.assertFalse(await plugin._download_latest())
            self.assertTrue(Path(packages, 'fprintd-1-1-x86_64.pkg.tar.zst').exists())

    async def test_seed_cache_copies_installed_versions_only_when_empty(self):
        with tempfile.TemporaryDirectory() as src, tempfile.TemporaryDirectory() as dst:
            for name in ('fprintd-2-1-x86_64.pkg.tar.zst', 'fprintd-2-1-x86_64.pkg.tar.zst.sig', 'libgusb-2-1-x86_64.pkg.tar.zst'):
                Path(src, name).touch()
            Path(dst, 'libgusb-1-1-x86_64.pkg.tar.zst').touch()
            plugin = bridge.Plugin(); plugin.packages = Path(dst)
            async def fake_cmd(timeout, *args): return 0, 'fprintd 2-1\nlibfprint 2-1\nlibgusb 2-1\n'
            plugin._cmd = fake_cmd
            with patch.object(bridge, 'PACMAN_CACHE', Path(src)):
                await plugin._seed_cache()
            self.assertEqual(sorted(p.name for p in Path(dst).iterdir()),
                             ['fprintd-2-1-x86_64.pkg.tar.zst', 'fprintd-2-1-x86_64.pkg.tar.zst.sig', 'libgusb-1-1-x86_64.pkg.tar.zst'])

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


