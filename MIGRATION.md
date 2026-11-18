# Standalone source transition

The installer retains its existing locked snapshot under
`adaptations/common/fingerprint`. The standalone bridge, upstream snapshot and
upstream lock are byte-identical to the retained files, checked by
`scripts/export-fingerprint-plugin.py` in the installer checkout. This source
also includes separate documentation and plugin tests. Model configuration remains in the OXP3 adaptation, and
native runtime construction remains separate. No installer package, maintenance
payload, recovery behavior or trust source was changed by this source split.

Export to a new directory using `python -B scripts/export-fingerprint-plugin.py
<new-directory>`; without an argument the command only checks the sources. The
export uses an explicit allowlist and prints sizes and SHA-256 hashes. It does
not create a Git repository. The installer does not yet bind its snapshot to an
independent repository commit. Before switching installer inputs,
review and pin an actual public commit, retain licenses and source verification,
and separately validate installation, maintenance, recovery, and hardware.

The standalone source includes an installer for an existing standard Decky
installation and independently installed fprintd commands. Installation,
upgrade, removal, duplicate detection, executable-path checks and restart
failure recovery have synthetic coverage, including Linux temporary fixtures.
Actual standard Decky installation and physical-device acceptance remain open.
The Boiler-managed OXP3 Decky path continues to use Boiler maintenance.

## v0.1.9 enrollment and FT9365 release gate

Game Mode adds a fingerprint list, a six-fingerprint limit, and a guided
procedure with eight accepted samples. After the fourth sample Decky prompts
for a grip change and fingertip-edge capture. The optional KDE agent displays
the touch keyboard inside the system authentication dialog.

The FT9365 driver requires sensor-confirmed lift between accepted samples.
Rejected frames can be retried immediately. The native release wait ends after
eight seconds and Decky ends a silent retry after twelve seconds. The X2 Mini
operator completed an enrollment successfully with these changes on the
current-boot preview. The existing fingerprints remained readable by fprintd.

The release combines the enrollment preview with verification against any
recorded finger and SteamOS package recovery from KevinX8. See the
[FT9365 provider and build scope](native/ft9365-release.md). The platform bound
native downloads are independent of the standalone Decky ZIP and the
Boiler installer and maintenance release.
