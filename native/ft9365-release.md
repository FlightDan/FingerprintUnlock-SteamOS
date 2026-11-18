# FT9365 enrollment for X2 Mini

The FT9365 lift requirement is enforced in the native libfprint driver.
`ft9365-release.patch` applies to the LF-normalized driver from
[SamSeven777/libfprint-fte3600 at 6efa376](https://github.com/SamSeven777/libfprint-fte3600/tree/6efa37679265f97973f6af15a18b375e3c5020a5).
It uses the sensor's calibrated Up event between accepted samples and releases
that wait after a rejected frame. Decky handles instructions, the eight-sample
progress, the edge prompt and the retry timeout. The existing template format
is shared with the previous driver.

The X2 Mini native release download contains the library and the KDE agent used
for the SteamOS 3.10 x86-64 test. The library uses the existing FTE3600 kernel
glue, fprintd service and OpenCV 4.6 runtime libraries with `.so.406` SONAMEs.
The KDE agent requires Qt and Qt Virtual Keyboard 6.11.1 and KDE Frameworks
6.28.0. The driver library, the authorization agent and their build sources are
available as separate release assets from the Decky plugin.

For an independently managed SteamOS system, build the patch into the matching
libfprint package and use that package's installation and rollback procedures.
Build and configure the optional KDE agent using the
[Game Mode keyboard instructions](../kde/gamescope-auth.md). For a
Boiler-managed installation, use its provider and maintenance workflow for
persistent installation. The hardware acceptance used a current-boot overlay
on the managed X2 Mini fingerprint service and Decky plugin.

The native patch is licensed under [LGPL-2.1-or-later](COPYING-LGPL-2.1).
The paired source archive keeps the upstream licenses and attributions.
