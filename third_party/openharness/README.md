# OpenHarness upstream reference

This directory carries the normative OpenHarness v1 draft Schema used by the
Legado Hub protocol boundary.

- Upstream: https://github.com/SynSwarm/OpenHarness
- Pinned source revision: `9c86454cf4f0b51e63ec081cb6bed7c84357968b`
- Upstream protocol: `docs/PROTOCOL.md`
- Upstream license: MIT; see `LICENSE`

Only the protocol Schema and license are vendored here. The upstream Shell
adapters are product-specific and are not runtime dependencies of this server.
Provider message conversion remains in `backend/app/infrastructure/providers`
behind the existing provider port.
