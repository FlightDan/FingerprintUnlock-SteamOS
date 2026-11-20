# Game Mode fingerprint authorization keyboard

`gamescope-auth.patch` applies to KDE's `polkit-kde-agent-1` v6.7.3,
commit `851bc2547ac6a9f0bdf072d642b17119906496ad`. It adds the Qt Virtual
Keyboard panel below the existing KDE fingerprint enrollment dialog, with an
explicit launch opt-in for the fprintd enrollment action. The KDE agent continues
handling the password and its response to Polkit.

For the X2 Mini preview, build against the 2026-07-16 Arch Linux Archive
snapshot (Qt 6.11.1, KDE Frameworks 6.28.0, PolkitQt 0.201.1). The build
requires CMake, Ninja, a C++20 compiler, Extra CMake Modules, Qt Base and
Declarative, PolkitQt6, KCoreAddons, KCrash, KDBusAddons, KI18n, Kirigami,
KNotifications, KWindowSystem and gettext. Check the installed SteamOS Qt
and KDE versions before using a binary from this build. The target also
requires the Qt 6 Virtual Keyboard runtime.

```sh
# Run from the repository root; the archive is a git archive of the pinned KDE commit.
echo 'fcd7e923aa09c6f897a61fe502e772c81978b125dd4c505a64b07a184c232659  kde/polkit-kde-agent-1-v6.7.3-source.tar.gz' | sha256sum -c -
tar -xzf kde/polkit-kde-agent-1-v6.7.3-source.tar.gz
cd polkit-kde-agent-1-6.7.3
patch -p1 < ../kde/gamescope-auth.patch
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr -DBUILD_TESTING=OFF
cmake --build build --target polkit-kde-authentication-agent-1
```

The bundled executable `kde/polkit-kde-authentication-agent-1-6.7.3` is the
158952-byte build with SHA-256
`959ef59018df7696a101479276b817faee5066d61eaae9b1ae51fa8776417d5f`.
The corresponding source archive, patch, build instructions, license and source lock are provided in this directory.
It was tested on SteamOS 3.10 with Qt 6.11.1 and KDE Frameworks 6.28.0;
the password field initially gains focus and displays the keyboard automatically.

The sudo standalone installer checks the SteamOS, Qt, KDE, agent and virtual
keyboard package versions before selecting this build by default. It installs a
separate immutable, root-owned copy under `/var/lib/boiler-fingerprint-standalone/`;
it does not replace the system agent. The copy remains as a shared cache after
uninstall. Unsupported systems continue to use the stock agent. An administrator
can build the source above and supply a trusted root-owned executable using
`--game-mode-auth-agent /path/to/agent` to override the default. The Decky-only
ZIP is lightweight and does not install this privileged copy: use `sudo sh
install.sh` for the automatic keyboard. The bridge launches the agent as the
active Steam user, and KDE and Polkit handle the password and authorization.
The KDE authorization agent patch is licensed under
[GPL-2.0-or-later](COPYING-GPL-2.0). The pinned KDE source retains the original notices.
