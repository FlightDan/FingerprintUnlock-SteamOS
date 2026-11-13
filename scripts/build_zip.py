#!/usr/bin/env python3
"""Build a Decky "install from zip" archive: python3 scripts/build_zip.py [out.zip]"""
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FOLDER = 'boiler-fingerprint-unlock'
FILES = {'main.py': 'bridge/main.py', 'dist/index.js': 'bridge/index.js', 'plugin.json': 'bridge/plugin.json',
         'package.json': 'bridge/package.json', 'LICENSE': 'COPYING', 'LICENSE-upstream': 'upstream/LICENSE'}
PROFILE = {'verify_command': '/usr/bin/fprintd-verify', 'list_command': '/usr/bin/fprintd-list',
           'enroll_command': '/usr/bin/fprintd-enroll'}

out = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / (FOLDER + '.zip'))
with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
    for name, src in FILES.items():
        z.write(ROOT / src, f'{FOLDER}/{name}')
    z.writestr(f'{FOLDER}/profile.json', json.dumps(PROFILE, indent=2) + '\n')
print(out)
