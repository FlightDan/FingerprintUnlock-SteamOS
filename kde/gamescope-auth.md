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
git clone --branch v6.7.3 --depth 1 https://github.com/KDE/polkit-kde-agent-1.git
cd polkit-kde-agent-1
test "$(git rev-parse HEAD)" = 851bc2547ac6a9f0bdf072d642b17119906496ad
git apply --check /path/to/FingerprintUnlock-SteamOS/kde/gamescope-auth.patch
git apply /path/to/FingerprintUnlock-SteamOS/kde/gamescope-auth.patch
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DCMAKE_INSTALL_PREFIX=/usr -DBUILD_TESTING=OFF
cmake --build build --target polkit-kde-authentication-agent-1
```

The resulting executable is `build/bin/polkit-kde-authentication-agent-1`.
Install it at a separate root-owned executable path with root-owned,
non-writable ancestors. Pass that path to `install.sh --game-mode-auth-agent`
when installing or upgrading the standalone plugin. The bridge opens that
agent as the active Steam user in Game Mode when an agent is required. Tap the
password field to show the keyboard below the controls. The root-owned copy is
managed by the administrator who supplies the option. Uninstalling the plugin
removes its configuration entry.

The KDE authorization agent patch is licensed under
[GPL-2.0-or-later](COPYING-GPL-2.0). The paired native source archive retains
KDE’s original notices.
