#!/usr/bin/env python3
"""Install the standalone plugin into an existing, standard Decky installation."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'boiler-fingerprint-unlock'
MARKER = '.boiler-fingerprint-standalone.json'
FILES = {'main.py': 'bridge/main.py', 'dist/index.js': 'bridge/index.js',
         'plugin.json': 'bridge/plugin.json', 'package.json': 'bridge/package.json'}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def command(*args):
    return subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)


def decky_home(explicit):
    if explicit:
        return Path(explicit).absolute()
    name = os.environ.get('SUDO_USER')
    if not name or name == 'root':
        raise ValueError('Specify --decky-home or run with sudo from the Decky user account')
    import pwd
    return Path(pwd.getpwnam(name).pw_dir) / 'homebrew'


def _security_stat(path):
    return path.stat()


def trusted_executable(path):
    # Check the lexical and resolved paths: a symlink may be used only when
    # its containing directory and the complete resolved path are trusted.
    path = Path(os.path.abspath(path))
    resolved = path.resolve(strict=True)
    directories = set(path.parents) | set(resolved.parents)
    for directory in directories:
        info = _security_stat(directory)
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError('fprintd path must be in root-owned directories that are not group/other writable')
    info = _security_stat(resolved)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
        raise ValueError('fprintd executable must be root-owned and not group/other writable')
    if not os.access(resolved, os.X_OK):
        raise ValueError('Required executable missing or not executable: ' + str(path))
    return str(resolved)


def preflight(home, bin_dir, require_binaries=True):
    plugins = home / 'plugins'
    if not home.is_dir() or not plugins.is_dir() or home.is_symlink() or plugins.is_symlink():
        raise ValueError('Existing Decky home and plugins directory required')
    unit = command('systemctl', 'cat', 'plugin_loader.service')
    if unit.returncode:
        raise ValueError('Existing Decky plugin_loader.service is required')
    if 'oxp3 managed offline decky' in unit.stdout.lower() or '/var/lib/oxp3-installer/decky' in unit.stdout.lower() or '/var/lib/oxp3-installer/decky' in str(home.resolve()).lower():
        raise ValueError('Boiler-managed OXP3 Decky must be managed through Boiler maintenance')
    binaries = {}
    for name in (('fprintd-verify', 'fprintd-list', 'fprintd-enroll') if require_binaries else ()):
        path = Path(bin_dir) / name
        try:
            binaries[name] = trusted_executable(path)
        except FileNotFoundError as exc:
            raise ValueError('Required executable missing: ' + str(path)) from exc
    return plugins, binaries


def manifest(target):
    marker = target / MARKER
    if marker.is_symlink() or not marker.is_file():
        raise ValueError('Existing plugin is not owned by this installer')
    try:
        data = json.loads(marker.read_text(encoding='utf-8'))
        hashes = data['files']
        if data['format'] != 1 or not isinstance(hashes, dict) or set(hashes) - (set(FILES) | {'profile.json'}):
            raise ValueError('invalid inventory')
        if not all(isinstance(v, str) and len(v) == 64 and all(c in '0123456789abcdef' for c in v) for v in hashes.values()):
            raise ValueError('invalid hashes')
        return hashes
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError('Invalid standalone plugin ownership record') from exc


def regular(path):
    return not path.is_symlink() and path.is_file() and not any(p.is_symlink() for p in path.parents if p.name == 'dist')


def restart_if_active(active):
    if active and command('systemctl', 'restart', 'plugin_loader.service').returncode:
        raise RuntimeError('Decky restart failed')
    if active and command('systemctl', 'is-active', '--quiet', 'plugin_loader.service').returncode:
        raise RuntimeError('Decky did not become active after restart')


def run(action, home, bin_dir):
    plugins, binaries = preflight(home, bin_dir, require_binaries=action != 'uninstall')
    target = plugins / FOLDER
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise ValueError('Plugin target is not an ordinary directory')
    old = manifest(target) if target.exists() else None
    if action == 'install':
        for other in plugins.iterdir():
            if other.name == FOLDER or not other.is_dir():
                continue
            metadata = other / 'plugin.json'
            try:
                if json.loads(metadata.read_text(encoding='utf-8')).get('name') == 'Boiler Fingerprint Unlock':
                    raise ValueError('Another Boiler Fingerprint Unlock plugin is already present; remove or manage it separately')
            except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
                continue
    if action == 'check':
        if old is None:
            print('Decky and fprintd commands found; plugin is not installed')
            return
        changed = [name for name, digest in old.items() if not regular(target / name) or sha((target / name).read_bytes()) != digest]
        if changed:
            raise ValueError('Installed files missing or changed: ' + ', '.join(changed))
        print('Decky, fprintd commands and standalone plugin inventory checked')
        return
    if action == 'uninstall' and old is None:
        raise ValueError('Standalone plugin is not installed')
    payload = {}
    if action == 'install':
        payload = {name: (ROOT / src).read_bytes() for name, src in FILES.items()}
        payload['profile.json'] = (json.dumps({'verify_command': binaries['fprintd-verify'], 'list_command': binaries['fprintd-list'], 'enroll_command': binaries['fprintd-enroll']}, indent=2) + '\n').encode()
    if action == 'install' and old is not None:
        for name in set(payload) | set(old):
            path = target / name
            if name in old:
                if not regular(path) or sha(path.read_bytes()) != old[name]:
                    raise ValueError('Refusing to overwrite changed or missing file: ' + name)
            elif os.path.lexists(path):
                raise ValueError('Refusing to overwrite unowned file: ' + name)
    active = command('systemctl', 'is-active', '--quiet', 'plugin_loader.service').returncode == 0
    staging_root = Path(tempfile.mkdtemp(prefix='.boiler-fingerprint-', dir=plugins))
    stage, backup = staging_root / 'new', staging_root / 'old'
    moved = False
    installed = False
    cleanup = True
    try:
        if target.exists():
            shutil.copytree(target, stage, symlinks=True)
        else:
            stage.mkdir()
        if action == 'install':
            for name, data in payload.items():
                path = stage / name
                if any(p.is_symlink() for p in (path, path.parent)):
                    raise ValueError('Linked plugin payload path refused: ' + name)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            hashes = {name: sha(data) for name, data in payload.items()}
        else:
            hashes = {}
            for name, digest in old.items():
                path = stage / name
                if regular(path) and sha(path.read_bytes()) == digest:
                    path.unlink()
                else:
                    hashes[name] = digest
            dist = stage / 'dist'
            if dist.is_dir() and not dist.is_symlink() and not any(dist.iterdir()):
                dist.rmdir()
        marker = stage / MARKER
        if hashes:
            marker.write_text(json.dumps({'format': 1, 'files': hashes}, indent=2) + '\n', encoding='utf-8')
        else:
            marker.unlink(missing_ok=True)
        if target.exists():
            target.rename(backup)
            moved = True
        if any(stage.iterdir()):
            stage.rename(target)
            installed = True
        restart_if_active(active)
    except Exception as exc:
        try:
            if installed:
                target.rename(stage)
            if moved:
                backup.rename(target)
        except OSError as recovery:
            cleanup = False
            raise RuntimeError(f'{exc}; file recovery failed: {recovery}; preserve {staging_root}') from exc
        if moved or installed:
            try:
                restart_if_active(active)
            except Exception as recovery:
                raise RuntimeError(f'{exc}; restored files but Decky restart also failed: {recovery}') from exc
        raise
    finally:
        if cleanup:
            shutil.rmtree(staging_root)
    if action == 'uninstall' and hashes:
        print('Removed unchanged managed files; modified files and ownership record retained')
    else:
        print('Standalone plugin ' + ('installed' if action == 'install' else 'uninstalled'))


def kde_pam():
    """Load the Plasma lock-screen installer that ships next to this script."""
    path = ROOT / 'kde' / 'install-kde-pam.py'
    spec = importlib.util.spec_from_file_location('kde_pam_install', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', nargs='?', choices=('install', 'check', 'uninstall', 'kde-pam'),
                        default='install')
    parser.add_argument('--decky-home', help='existing Decky homebrew directory')
    parser.add_argument('--fprintd-bin', default='/usr/bin', help='directory containing fprintd CLI programs')
    parser.add_argument('--kde-pam-package',
                        help='kde-pam action: fprintd package archive providing usr/lib/security/pam_fprintd.so')
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise ValueError('Run with sudo')
        if args.action == 'kde-pam':
            module = kde_pam()
            if args.kde_pam_package:
                print(json.dumps(module.install(args.kde_pam_package), indent=2))
            else:
                return module.check()
            return 0
        run(args.action, decky_home(args.decky_home), args.fprintd_bin)
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print('Error: ' + str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
