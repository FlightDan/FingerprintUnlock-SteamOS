# Boiler Fingerprint Unlock

This directory is the source snapshot for a standalone Decky fingerprint unlock
plugin. `bridge/` contains the Boiler implementation; `upstream/` retains the
MIT-licensed source and notice from `podothecat/decky-fingerprint-unlock` at the
commit and file hashes in `source-lock.json`. Boiler changes retain the project's
AGPL license; see `COPYING`. The upstream MIT license remains in
`upstream/LICENSE`.

The bridge expects a separately supplied device profile and native fprint
runtime. This repository does not supply device identity, installation,
enrollment, authentication policy, or recovery configuration. Those belong to
the integrator and the applicable device adaptation. Fingerprint verification
does not replace the PIN recovery path.

Run the isolated checks from this directory with `python -B -m unittest discover
-s tests -p 'test_*.py'` and `node tests/fingerprint_decky_smoke.mjs
bridge/index.js`. These checks use mocks and do not establish device or SteamOS
compatibility. Integration and hardware acceptance are separate.
