# Protocol Governance

This directory contains mutable governance material rather than published protocol snapshots.

- `protocol_history.json` is a compatibility mirror for recognized legacy releases. Its contents must match the legacy release entries in `../catalog/release_manifest.json`.
- `../catalog/release_manifest.json` is the only authority for release lifecycle, migration targets, the default new-flow version, and published artifact paths.

Published protocol artifacts live below their protocol category and version directory. Each release directory keeps its specification, machine snapshot, vocabulary, and referenced Base tool-pack contract together. These paths are release evidence; moving them requires a catalog migration and governance audit.
