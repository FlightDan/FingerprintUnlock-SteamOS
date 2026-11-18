#!/usr/bin/env python3
"""Build a Decky "install from zip" archive: python3 scripts/build_zip.py [out.zip]"""
import importlib.util
import json
from pathlib import Path
import sys
import zipfile

spec = importlib.util.spec_from_file_location('standalone_installer', Path(__file__).with_name('install.py'))
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)
ROOT, FOLDER = installer.ROOT, installer.FOLDER
FILES = {**installer.FILES, 'LICENSE': 'COPYING', 'LICENSE-upstream': 'upstream/LICENSE'}
PROFILE = installer.command_profile(installer.STOCK_COMMANDS)

out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / (FOLDER + '.zip'))
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for name, src in FILES.items():
        z.write(ROOT / src, f'{FOLDER}/{name}')
    z.writestr(f'{FOLDER}/profile.json', json.dumps(PROFILE, indent=2) + '\n')
print(out)
