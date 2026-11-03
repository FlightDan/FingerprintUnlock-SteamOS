# Fingerprint Unlock for SteamOS

![Lock screen preview (mockup)](assets/preview.png)

A Decky plugin for unlocking SteamOS with a fingerprint while keeping PIN unlock available. The image above is a mockup; compatibility depends on your device and fingerprint driver.

## Installation

Install Decky Loader, your fingerprint driver and fprintd first, and enroll a fingerprint. From this repository's directory, run:

```sh
sudo sh install.sh
```

The installer uses `/usr/bin` for fprintd tools by default; use `--fprintd-bin /path/to/bin` for a root-managed alternative. On a Boiler-managed OXP3, use Boiler maintenance instead.

## License

Boiler code: [AGPL-3.0](COPYING). The bundled upstream project retains its [MIT license](upstream/LICENSE).
