import asyncio
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch, AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('fingerprint_bridge', ROOT / 'bridge/main.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class VerificationTests(unittest.IsolatedAsyncioTestCase):
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
        self.assertEqual(spawn.call_args.kwargs['env'], {'PATH': '/usr/bin:/bin', 'LANG': 'C'})


    async def test_failure_cancel_and_partial_match_cannot_unlock(self):
        plugin = bridge.Plugin()
        plugin.lock = asyncio.Lock()
        plugin.verify_path = '/nonexistent'
        for code, output, cancelled in [(1, 'Verify result: verify-match (done)', False),
                (0, 'verify-match', False), (None, '', False),
                (0, 'Verify result: verify-no-match (done)\nVerify result: verify-match (done)', False),
                (0, 'Verify result: verify-match (done)', True)]:
            async def fake_run(path, timeout):
                plugin.cancelled = cancelled
                return code, output, None
            plugin._run = fake_run
            self.assertNotEqual((await plugin.verify())['result'], 'match')
        async def success(path, timeout):
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
            async def fake_run(path, timeout): return code, output, reason
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


