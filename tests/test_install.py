import importlib.util
import json
from pathlib import Path
import tempfile
import stat
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/install.py'
spec = importlib.util.spec_from_file_location('standalone_install', SCRIPT)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Result:
    def __init__(self, code=0, stdout=''):
        self.returncode, self.stdout = code, stdout


class InstallTests(unittest.TestCase):
    def test_shell_scripts_use_lf_line_endings(self):
        root = SCRIPT.parents[1]
        self.assertIn('*.sh text eol=lf', (root / '.gitattributes').read_text().splitlines())
        for path in (root / 'install.sh', root / 'install-online.sh',
                     root / 'tests/test_install_online.sh'):
            with self.subTest(path=path):
                self.assertNotIn(b'\r', path.read_bytes())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'homebrew'
        (self.home / 'plugins').mkdir(parents=True)
        self.bin = Path(self.tmp.name) / 'bin'
        self.bin.mkdir()
        for name in ('fprintd-verify', 'fprintd-list', 'fprintd-enroll'):
            (self.bin / name).write_text('mock')
        self.commands = []
        self.fail_restart = False
        self.service = 'ExecStart=/home/deck/homebrew/services/PluginLoader\n'
        self.security = {}
        self.patches = [patch.object(installer, '_security_stat', side_effect=self.security_stat),
                        patch.object(installer.os, 'access', return_value=True),
                        patch.object(installer, 'command', side_effect=self.command)]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        self.target = self.home / 'plugins' / installer.FOLDER

    def security_stat(self, path):
        if path in self.security:
            return self.security[path]
        return SimpleNamespace(st_uid=0, st_mode=(stat.S_IFDIR | 0o755) if path.is_dir() else (stat.S_IFREG | 0o755))

    def command(self, *args):
        self.commands.append(args)
        if args[1] == 'cat':
            return Result(stdout=self.service)
        if args[1] == 'restart' and self.fail_restart:
            self.fail_restart = False
            return Result(1)
        return Result()

    def run_action(self, action):
        installer.run(action, self.home, self.bin)

    def test_install_upgrade_and_uninstall_preserve_unknown_files(self):
        self.run_action('install')
        profile = json.loads((self.target / 'profile.json').read_text())
        self.assertEqual(profile['verify_command'], str((self.bin / 'fprintd-verify').resolve()))
        (self.target / 'notes.txt').write_text('keep')
        self.run_action('check')
        self.run_action('install')
        self.run_action('uninstall')
        self.assertEqual((self.target / 'notes.txt').read_text(), 'keep')
        self.assertFalse((self.target / 'main.py').exists())

    def test_modified_files_are_never_overwritten_or_deleted(self):
        self.run_action('install')
        (self.target / 'main.py').write_text('custom')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.run_action('install')
        self.run_action('uninstall')
        self.assertEqual((self.target / 'main.py').read_text(), 'custom')
        self.assertTrue((self.target / installer.MARKER).is_file())

    def test_unowned_target_and_managed_decky_rejected(self):
        self.target.mkdir()
        with self.assertRaisesRegex(ValueError, 'not owned'):
            self.run_action('install')
        self.target.rmdir()
        self.service = 'ExecStart=/var/lib/oxp3-installer/decky/runtime/services/PluginLoader'
        with self.assertRaisesRegex(ValueError, 'Boiler maintenance'):
            self.run_action('install')
        self.assertFalse(self.target.exists())

    def test_missing_cli_prevents_mutation(self):
        (self.bin / 'fprintd-list').unlink()
        with self.assertRaisesRegex(ValueError, 'Required executable'):
            self.run_action('install')
        self.assertFalse(self.target.exists())

    def test_duplicate_plugin_name_blocks_install_but_not_maintenance(self):
        self.run_action('install')
        duplicate = self.home / 'plugins' / 'another-fingerprint-plugin'
        duplicate.mkdir()
        (duplicate / 'plugin.json').write_text(json.dumps({'name': 'Boiler Fingerprint Unlock'}))
        with self.assertRaisesRegex(ValueError, 'already present'):
            self.run_action('install')
        self.run_action('check')
        self.run_action('uninstall')
        self.assertTrue((duplicate / 'plugin.json').is_file())

    def test_untrusted_fprintd_target_or_ancestor_is_rejected(self):
        executable = (self.bin / 'fprintd-verify').resolve()
        for path, mode, uid in ((executable, stat.S_IFREG | 0o777, 0),
                                (executable, stat.S_IFREG | 0o755, 1000),
                                (self.bin.resolve(), stat.S_IFDIR | 0o775, 0)):
            with self.subTest(path=path, mode=mode, uid=uid):
                self.security[path] = SimpleNamespace(st_uid=uid, st_mode=mode)
                with self.assertRaisesRegex(ValueError, 'root-owned'):
                    self.run_action('install')
                self.assertFalse(self.target.exists())
                self.security.clear()
        self.run_action('install')
        self.assertTrue(self.target.exists())

    def test_uninstall_after_fprintd_removal(self):
        self.run_action('install')
        for path in self.bin.iterdir():
            path.unlink()
        self.run_action('uninstall')
        self.assertFalse(self.target.exists())

    def test_restart_failure_restores_previous_installation(self):
        self.run_action('install')
        before = (self.target / installer.MARKER).read_bytes()
        self.fail_restart = True
        with self.assertRaisesRegex(RuntimeError, 'restart failed'):
            self.run_action('uninstall')
        self.assertEqual((self.target / installer.MARKER).read_bytes(), before)
        self.assertTrue((self.target / 'main.py').exists())

    def test_kde_pam_loader_resolves_the_shipped_tool(self):
        module = installer.kde_pam()
        self.assertEqual(Path(module.__file__).resolve(),
                         (SCRIPT.parents[1] / 'kde' / 'install-kde-pam.py').resolve())
        for name in ('install', 'check', 'uninstall'):
            self.assertTrue(callable(getattr(module, name)))


if __name__ == '__main__':
    unittest.main()


