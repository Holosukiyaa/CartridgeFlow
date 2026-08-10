# Compiled Protocol Registry

`protocol-registry.sqlite` is the read-only product governance knowledge base.
It contains complete protocol artifacts and searchable sections for both
`current` and `temp-runtime`, plus the Base implementation evidence and an
explicit allowlist of committed `config/` documentation, defaults and safe
templates. Runtime reads default to `current`; the second line is present for
governance and comparison, never implicit merging.

The allowlist is intentionally fixed rather than recursively scanned. Runtime
state and production data under `.data/`, credentials, generated databases,
lock files and viewer implementation files are never copied into this database.

`protocol-registry.lock.json` pins the authoritative `protocol-source.sqlite`
to one full Git commit, its source database SHA-256 and logical digest. It also
pins the published product database SHA-256.

Protocol originals live at:

```text
../../protocol-source/protocol-source.sqlite
```

`protocol-source/` is a Git submodule backed by
https://github.com/Holosukiyaa/cartridgeflow-protocols.

Do not edit this product database directly. Update the authoritative source
database with `protocol-source/scripts/protocol_db.py`, verify it, commit and
push the submodule repository, then
publish from the CartridgeFlow repository:

```powershell
python scripts/update_protocol_registry.py
python scripts/audit_protocol_governance.py
```

For local read-only browsing, run `view-protocols.bat` from the repository root.
The Chinese portal at `http://127.0.0.1:8001/` exposes the authoritative source
and this product snapshot as separate knowledge areas.
