# Standalone source transition

The installer retains its existing locked snapshot under
`adaptations/common/fingerprint`. The standalone source is currently a
byte-identical copy, checked by `scripts/export-fingerprint-plugin.py` in the
installer checkout. Model configuration remains in the OXP3 adaptation, and
native runtime construction remains separate. No installer package, maintenance
payload, recovery behavior or trust source was changed by this source split.

Export to a new directory using `python -B scripts/export-fingerprint-plugin.py
<new-directory>`; without an argument the command only checks the sources. The
export uses an explicit allowlist and prints sizes and SHA-256 hashes. It does
not create a Git repository. The independent repository and its commit binding
are pending; no such commit is asserted here. Before switching installer inputs,
review and pin an actual public commit, retain licenses and source verification,
and separately validate installation, maintenance, recovery, and hardware.
