# Fingerprint Unlock for SteamOS

![Lock screen preview with avatar concealed](assets/preview.png)

A Decky plugin for unlocking SteamOS with a fingerprint while keeping PIN unlock available. Compatibility depends on your device and fingerprint driver.

## Installation

Install Decky Loader, your fingerprint driver and fprintd first, and enroll a fingerprint. Run as your normal user:

```sh
curl -fsSL https://raw.githubusercontent.com/FlightDan/FingerprintUnlock-SteamOS/2c2578cffd68c2eed4add069fa4b677948ba67e5/install-online.sh | sh
```

For an offline checkout, run from the repository directory:

```sh
sudo sh install.sh
```

The installer uses `/usr/bin` for fprintd tools by default; use `--fprintd-bin /path/to/bin` for a root-managed alternative. On a Boiler-managed OXP3, use Boiler maintenance instead.

## Plasma desktop unlock

The Decky plugin covers the Steam game-mode lock screen. Plasma's own lock screen uses a different mechanism: `kscreenlocker_greet` starts a non-interactive PAM authenticator with the service name `kde-fingerprint`. The `kscreenlocker` package already installs that service file under `/usr/lib/pam.d/`, and it already calls `pam_fprintd.so`. What SteamOS lacks is the module itself, because it does not preinstall the Arch `fprintd` package.

Install the module from a reviewed package archive:

```sh
sudo python3 kde/install-kde-pam.py install --package /path/to/fprintd-1.94.5-2-x86_64.pkg.tar.zst
```

Or through the main entry point:

```sh
sudo python3 scripts/install.py kde-pam --kde-pam-package /path/to/fprintd-1.94.5-2-x86_64.pkg.tar.zst
sudo python3 scripts/install.py kde-pam     # check only
```

`uninstall` and `check` are also available directly on `kde/install-kde-pam.py`. See [kde/README.md](kde/README.md) for the verified behaviour, including why the vendor `-auth` line cannot authenticate a user on its own.

This installs one file, `/usr/lib/security/pam_fprintd.so`, and never rewrites a PAM service file.

There is no setting to enable this in System Settings. Plasma shows the fingerprint prompt exactly when the non-interactive authenticator reports itself available; the password field is always present. On an ONEXPLAYER X2 Mini with an FTE3600 sensor the prompt appeared and the enrolled finger unlocked a locked session.

## License

Boiler code: [AGPL-3.0](COPYING). The bundled upstream project retains its [MIT license](upstream/LICENSE).
