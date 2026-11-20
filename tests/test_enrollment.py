import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

spec = importlib.util.spec_from_file_location('bridge_enroll', Path(__file__).resolve().parents[1] / 'bridge/main.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class EnrollmentTests(unittest.IsolatedAsyncioTestCase):
    def plugin(self):
        p = bridge.Plugin(); p.lock = asyncio.Lock(); p.proc = None; p.cancelled = False
        p.enroll_state = None; p.enroll_unit = None; p.enroll_command = '/fixture/fprintd-enroll -f right-index-finger'
        p.list_path = '/fixture/fprintd-list'
        p.game_mode_auth_agent = None
        p.enroll_profile = {'total': 8, 'guided': True, 'scan_type': 'press'}
        p._account = lambda: SimpleNamespace(pw_name='deck', pw_uid=1000, pw_gid=1000, pw_dir='/home/deck')
        return p

    async def test_existing_any_finger_verification_shares_enrollment_lock(self):
        p = self.plugin()
        p.verify_path = '/fixture/fprintd-verify'
        p._run = AsyncMock(return_value=(0, 'Verify result: verify-match (done)\n', None))
        self.assertEqual(await p.verify(), {'result': 'match'})
        p._run.assert_awaited_once_with('/fixture/fprintd-verify', 30, '-f', 'any')
        async with p.lock:
            self.assertEqual(await p.verify(), {'result': 'busy'})
            self.assertEqual(await p.enroll(), {'result': 'busy'})

    async def test_inventory_reads_existing_and_checks_reader(self):
        p = self.plugin()
        p._user_capture = AsyncMock(side_effect=[(0, 'o "/net/reactivated/Fprint/Device/0"\n'),
            (0, 's "FocalTech FTE3600 (host BRISK)"\n'), (0, 'i 9\n'),
            (0, 'found 1 devices\nDevice at /net/reactivated/Fprint/Device/0\nUsing device /net/reactivated/Fprint/Device/0\nFingerprints for user deck on FocalTech FTE3600 (host BRISK) (press):\n - #0: left-index-finger\n - #1: right-index-finger\n')])
        self.assertEqual(await p.fingerprints(), {'result': 'available', 'count': 2, 'limit': 6})
        other = 'found 1 devices\nDevice at /net/reactivated/Fprint/Device/0\nUsing device /net/reactivated/Fprint/Device/0\nFingerprints for user deck on Other reader (swipe):\n - #0: right-thumb\n'
        p._user_capture = AsyncMock(side_effect=[(0, 'o "/net/reactivated/Fprint/Device/0"\n'),
            (0, 's "Other reader"\n'), (0, 'i -1\n'), (0, other)])
        self.assertEqual(await p._list_fingerprints(), ['right-thumb'])
        self.assertEqual(p.enroll_profile, {'total': None, 'guided': False, 'scan_type': 'swipe'})

    async def test_list_requires_complete_recognized_output(self):
        p = self.plugin()
        prefix = [(0, 'o "/net/reactivated/Fprint/Device/0"\n'), (0, 's "FocalTech FTE3600 (host BRISK)"\n'), (0, 'i 9\n')]
        base = 'found 1 devices\nDevice at /net/reactivated/Fprint/Device/0\nUsing device /net/reactivated/Fprint/Device/0\n'
        empty = 'User deck has no fingers enrolled for FocalTech FTE3600 (host BRISK).\n'
        p._user_capture = AsyncMock(side_effect=prefix + [(0, base + empty), (0, 's "swipe"\n')])
        self.assertEqual(await p.fingerprints(), {'result': 'available', 'count': 0, 'limit': 6})
        self.assertEqual(p.enroll_profile['scan_type'], 'swipe')
        for bad in ('found 0 devices\n', base, base + 'Fingerprints for user deck on FocalTech FTE3600 (host BRISK) (press):\n', base + empty + 'error\n', base.replace('Device/0', 'Device/1') + empty):
            p._user_capture = AsyncMock(side_effect=prefix + [(0, bad)])
            self.assertIsNone(await p._list_fingerprints())

    async def test_generic_reader_completion_uses_its_own_stage_count(self):
        p = self.plugin()
        async def fingerprint_list():
            p.enroll_profile = {'total': None, 'guided': False, 'scan_type': 'press'}
            return []
        p._list_fingerprints = AsyncMock(side_effect=fingerprint_list)
        p._prepare_game_mode_auth = AsyncMock(return_value=None)
        p._stop_unit = AsyncMock(return_value=True)
        p._stop = AsyncMock()
        reader = asyncio.StreamReader()
        reader.feed_data(b'Enroll result: enroll-stage-passed\nEnroll result: enroll-completed\n')
        reader.feed_eof()
        p._user_process = AsyncMock(return_value=SimpleNamespace(stdout=reader, wait=AsyncMock(), returncode=0))
        result = await p.enroll()
        self.assertEqual(result, {'result': 'complete', 'samples': 2, 'total': None, 'guided': False, 'scan_type': 'press'})

    async def test_malformed_result_line_is_rejected(self):
        _, result = await self.run_events(['enroll-stage-passed', 'garbled (done)'] + ['enroll-stage-passed'] * 7 + ['enroll-completed'])
        self.assertEqual(result['result'], 'unavailable')
    async def test_unknown_terminal_rejected(self):
        _, result = await self.run_events(['enroll-stage-passed', 'enroll-failed', 'enroll-stage-passed'] + ['enroll-stage-passed'] * 7 + ['enroll-completed'])
        self.assertEqual(result['result'], 'unavailable')
    async def run_events(self, events, *, output=None, code=0, close_output=True):
        p = self.plugin()
        async def fingerprint_list():
            p.enroll_profile = {'total': 8, 'guided': True, 'scan_type': 'press'}
            return ['left-index-finger', 'right-index-finger']
        p._list_fingerprints = AsyncMock(side_effect=fingerprint_list)
        p._prepare_game_mode_auth = AsyncMock(return_value=None)
        p._stop_unit = AsyncMock(return_value=True); p._stop = AsyncMock()
        reader = asyncio.StreamReader()
        for event in events:
            reader.feed_data(('Enroll result: ' + event + '\n').encode())
        if output:
            reader.feed_data((output + '\n').encode())
        if close_output:
            reader.feed_eof()
        proc = SimpleNamespace(stdout=reader, wait=AsyncMock(), returncode=code)
        p._user_process = AsyncMock(return_value=proc)
        result = await p.enroll()
        return p, result

    async def test_identification_plus_eight_samples_and_legacy_argv(self):
        p, result = await self.run_events(['enroll-stage-passed'] * 8 + ['enroll-completed'])
        self.assertEqual(result, {'result': 'complete', 'samples': 8, 'total': 8, 'guided': True, 'scan_type': 'press'})
        args = p._user_process.await_args.args
        self.assertEqual(args[-4:], ('/fixture/fprintd-enroll', '-f', 'right-middle-finger', 'deck'))
        self.assertIn('--user', args); self.assertIn('--pipe', args); self.assertIn('--wait', args); self.assertIn('--setenv=LC_ALL=C', args)
        p._stop_unit.assert_awaited_once()

    async def test_retry_does_not_count_and_early_completion_fails(self):
        _, result = await self.run_events(['enroll-stage-passed', 'enroll-retry-scan', 'enroll-completed'])
        self.assertEqual(result['result'], 'unavailable')
        self.assertEqual(result['samples'], 0)

    async def test_stalled_retry_times_out_and_releases_the_enrollment(self):
        with patch.object(bridge, 'ENROLL_RETRY_TIMEOUT_SECONDS', 0.01):
            p, result = await self.run_events(
                ['enroll-stage-passed', 'enroll-stage-passed', 'enroll-remove-and-retry'],
                close_output=False)
        self.assertEqual(result, {'result': 'unavailable', 'reason': 'retry-timeout', 'samples': 1})
        p._stop_unit.assert_awaited_once()
        p._stop.assert_awaited_once()
        self.assertIsNone(p.enroll_unit)
        self.assertFalse(p.lock.locked())

    async def test_enrollment_cap_is_rechecked_before_any_spawn(self):
        p = self.plugin()
        p._list_fingerprints = AsyncMock(return_value=list(bridge.FINGER_SLOTS[:6]))
        p._stop_unit = AsyncMock(return_value=True)
        p._user_process = AsyncMock()
        p._prepare_game_mode_auth = AsyncMock()
        self.assertEqual(await p.enroll(), {'result': 'full'})
        p._user_process.assert_not_awaited()
        p._prepare_game_mode_auth.assert_not_awaited()

    async def test_authorization_denial_is_distinct_from_capture_failure(self):
        _, result = await self.run_events([], output='EnrollStart failed: GDBus.Error:net.reactivated.Fprint.Error.PermissionDenied: Not Authorized: net.reactivated.fprint.device.enroll', code=1)
        self.assertEqual(result['reason'], 'authorization')
        _, result = await self.run_events(['enroll-duplicate'], code=1)
        self.assertEqual(result['reason'], 'duplicate')

    async def test_game_mode_starts_native_agent_on_gamescope_display(self):
        p = self.plugin()
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'),
                                                   (1, ''), (0, ''), (0, 'PID=448\n')])
        self.assertEqual(await p._prepare_game_mode_auth(), (':3', '448'))
        args = p._user_capture.await_args_list[3].args
        self.assertIn('--user', args)
        self.assertIn('--setenv=DISPLAY=:3', args)
        self.assertIn('--setenv=QT_SCALE_FACTOR=1.6', args)
        self.assertIn('--property=BindsTo=gamescope-session.target', args)
        self.assertEqual(args[-1], '/usr/lib/polkit-kde-authentication-agent-1')
        self.assertNotIn('--setenv=QT_IM_MODULE=qtvirtualkeyboard', args)

    async def test_preview_agent_uses_embedded_keyboard_in_game_mode(self):
        p = self.plugin()
        p.game_mode_auth_agent = '/opt/boiler/polkit-kde-authentication-agent-1'
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'),
                                                 (1, ''), (0, ''), (0, 'PID=448\n')])
        self.assertEqual(await p._prepare_game_mode_auth(), (':3', '448'))
        args = p._user_capture.await_args_list[3].args
        self.assertIn('--setenv=BOILER_FINGERPRINT_GAMESCOPE_KEYBOARD=1', args)
        self.assertIn('--setenv=QT_IM_MODULE=qtvirtualkeyboard', args)
        self.assertIn('--setenv=QT_VIRTUALKEYBOARD_DESKTOP_DISABLE=1', args)
        self.assertEqual(args[-2:], ('--', p.game_mode_auth_agent))

    async def test_session_with_existing_agent_does_not_start_another(self):
        p = self.plugin()
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'), (0, 'PID=448\n')])
        self.assertEqual(await p._prepare_game_mode_auth(), (':3', '448'))
        self.assertEqual(p._user_capture.await_count, 3)

    async def test_upgrade_replaces_only_our_stale_agent(self):
        p = self.plugin()
        p.game_mode_auth_agent = '/opt/boiler/polkit-kde-authentication-agent-1'
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'),
            (0, 'PID=448\n'), (0, '448\n'), (0, '/usr/lib/polkit-kde-authentication-agent-1\n'),
            (1, ''), (0, ''), (0, 'PID=449\n')])
        p._stop_unit = AsyncMock(return_value=True)
        self.assertEqual(await p._prepare_game_mode_auth(), (':3', '449'))
        p._stop_unit.assert_awaited_once_with('boiler-fingerprint-gamemode-auth.service')
        self.assertEqual(p._user_capture.await_args_list[-2].args[-1], p.game_mode_auth_agent)

    async def test_other_agent_is_never_stopped(self):
        p = self.plugin()
        p.game_mode_auth_agent = '/opt/boiler/polkit-kde-authentication-agent-1'
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'),
                                                  (0, 'PID=448\n'), (0, '999\n')])
        p._stop_unit = AsyncMock()
        self.assertEqual(await p._prepare_game_mode_auth(), (':3', '448'))
        p._stop_unit.assert_not_awaited()

    async def test_failed_stale_agent_stop_aborts(self):
        p = self.plugin()
        p.game_mode_auth_agent = '/opt/boiler/polkit-kde-authentication-agent-1'
        p._user_capture = AsyncMock(side_effect=[(0, ''), (0, 'DISPLAY=:3\n'),
            (0, 'PID=448\n'), (0, '448\n'), (0, '/usr/lib/polkit-kde-authentication-agent-1\n')])
        p._stop_unit = AsyncMock(return_value=False)
        self.assertFalse(await p._prepare_game_mode_auth())
    async def test_game_mode_positions_and_focuses_only_agent_window(self):
        p = self.plugin()
        p.enroll_state = {'result': 'identifying', 'samples': 0}
        p._user_capture = AsyncMock(side_effect=[
            (0, '231\n'), (0, '1920 1200\n'),
            (0, 'WINDOW=231\nWIDTH=1008\nHEIGHT=229\n'),
            (0, ''), (0, ''), (0, '')
        ])
        await p._focus_game_mode_auth(':3', '448')
        calls = [entry.args for entry in p._user_capture.await_args_list]
        self.assertEqual(calls[0][-2:], ('--pid', '448'))
        self.assertEqual(calls[3][-4:], ('windowmove', '231', '456', '120'))
        self.assertIn('STEAM_OVERLAY', calls[4])
        self.assertIn('STEAM_INPUT_FOCUS', calls[5])
        self.assertEqual(calls[4][3:5], ('-id', '231'))
        self.assertEqual(p.enroll_state, {'result': 'identifying', 'samples': 0})

    async def test_duplicate_completion_is_rejected(self):
        _, result = await self.run_events(['enroll-stage-passed'] * 8 + ['enroll-completed', 'enroll-completed'])
        self.assertEqual(result['result'], 'unavailable')
    async def test_cancel_stops_transient_unit(self):
        p = self.plugin(); p.enroll_unit = 'test.service'; p._stop_unit = AsyncMock(return_value=True); p._stop = AsyncMock()
        p.proc = object()
        await p.cancel()
        p._stop_unit.assert_awaited_once_with('test.service'); p._stop.assert_awaited_once()
        self.assertTrue(p.cancelled)

    async def test_failed_stop_is_reported_and_unit_is_retained(self):
        p = self.plugin(); p.enroll_unit = 'test.service'; p._stop_unit = AsyncMock(return_value=False)
        self.assertEqual(await p.cancel(), {'cancelled': False})
        self.assertEqual(p.enroll_unit, 'test.service')
        self.assertEqual((await p.enroll())['result'], 'busy')

    async def test_stop_confirms_inactive_state_after_failure(self):
        p = self.plugin(); p._user_capture = AsyncMock(side_effect=[(1, 'failed'), (0, 'LoadState=loaded\nActiveState=inactive\n')])
        self.assertTrue(await p._stop_unit('test.service'))
        p._user_capture = AsyncMock(side_effect=[(1, 'failed'), (0, 'LoadState=loaded\nActiveState=active\n')])
        self.assertFalse(await p._stop_unit('test.service'))

    async def test_too_fast_is_retry(self):
        _, result = await self.run_events(['enroll-stage-passed', 'enroll-too-fast'] + ['enroll-stage-passed'] * 7 + ['enroll-completed'])
        self.assertEqual(result['result'], 'complete')
    async def test_spawn_uses_current_user_and_user_bus(self):
        p = self.plugin(); proc = object()
        with patch.object(bridge.os, 'getgrouplist', return_value=[1000, 10], create=True), patch.object(bridge.asyncio, 'create_subprocess_exec', new=AsyncMock(return_value=proc)) as spawn:
            await p._user_process('/usr/bin/systemd-run', '--user')
        self.assertEqual(spawn.call_args.args, ('/usr/bin/systemd-run', '--user'))
        kw = spawn.call_args.kwargs
        self.assertEqual((kw['user'], kw['group'], kw['extra_groups']), (1000, 1000, [1000, 10]))
        self.assertEqual(kw['env']['DBUS_SESSION_BUS_ADDRESS'], 'unix:path=/run/user/1000/bus')

if __name__ == '__main__': unittest.main()
