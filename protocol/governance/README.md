# Protocol Governance

This directory contains mutable governance material rather than published protocol snapshots.

- `protocol_history.json` is a compatibility mirror for recognized legacy releases. Its contents must match the legacy release entries in `../catalog/release_manifest.json`.
- `../catalog/release_manifest.json` is the only authority for release lifecycle, migration targets, the default new-flow version, and published artifact paths.

Published CF-FARP snapshots, vocabulary snapshots, the Base Contract identity, and tool-pack registry remain in their respective category directories. Their paths are stable published evidence and must not be moved during ordinary repository cleanup.
