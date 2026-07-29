# Protocol Documents

Protocol documents are grouped by their role. `protocol/catalog/release_manifest.json`
is the machine-readable authority for release lifecycle, default versions, and
the canonical document path for each CF-FARP release.

```text
docs/protocol/
  base-contract/    Base Contract release documents
  flow-authoring/   CF-FARP release documents
  governance/       Human-readable protocol governance rules
```

Use the latest document referenced by the release manifest for active work.
Historical documents remain immutable release evidence; add a new version rather
than rewriting an older protocol document.
