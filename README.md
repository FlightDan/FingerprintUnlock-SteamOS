# Boiler Fingerprint Unlock

This standalone Decky plugin uses an existing fprintd installation. Install the
fingerprint driver and fprintd for your device yourself first, and retain a PIN
recovery path. This script does not install drivers, configure system services,
PAM, udev or polkit, or enroll a fingerprint.

On Linux with an existing standard Decky installation, run from this directory:

```sh
sudo sh install.sh
sudo sh install.sh check
sudo sh install.sh uninstall
```

The default Decky location is the invoking sudo user's passwd home followed by
`homebrew/plugins`. For a nonstandard location specify the existing homebrew
folder: `sudo sh install.sh install --decky-home /path/to/homebrew`. The script
requires the existing `plugin_loader.service` and executable `fprintd-verify`,
`fprintd-list`, and `fprintd-enroll` in `/usr/bin`; use `--fprintd-bin /path`
to choose their directory. The executable targets and all path directories must
be owned by root and not writable by group or other users; use a root-managed
directory for custom commands. It generates a plugin profile for those commands.
The script does not verify a driver, fingerprint sensor, or enrollment; follow
your device's instructions for enrollment separately.

The script refuses Boiler-managed OXP3 Decky installations: use Boiler
maintenance for those installations. It refuses an existing plugin it does not
own and will not overwrite changed managed files. Unknown files are preserved;
uninstall removes only unchanged managed files, leaving changed files and their
ownership record. When Decky is active, the script restarts it after changes;
on failure it restores the previous plugin files and attempts to restart Decky.
Review any reported recovery error before retrying.

`bridge/` contains the Boiler implementation; `upstream/` retains the
MIT-licensed source and notice from `podothecat/decky-fingerprint-unlock` at the
commit and file hashes in `source-lock.json`. Boiler changes retain the project's
AGPL license; see `COPYING`. The upstream MIT license remains in
`upstream/LICENSE`.

Run isolated checks with `python3 -B -m unittest discover -s tests -p
"test_*.py"` and `node tests/fingerprint_decky_smoke.mjs bridge/index.js`.
These use mocks and do not establish device or SteamOS compatibility. Standard
Decky integration, recovery and physical hardware acceptance remain unverified.
