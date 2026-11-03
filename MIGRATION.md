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
