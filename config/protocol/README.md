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

Protocol originals live only in the independent
https://github.com/Holosukiyaa/cartridgeflow-protocols repository. This product
does not embed or mount that repository.

Do not edit this product database directly. Update and verify the authoritative
database in a separate checkout, commit and push that repository, then publish
from the CartridgeFlow repository with the checkout passed explicitly:

```powershell
python scripts/update_protocol_registry.py --protocol-repository C:\path\to\cartridgeflow-protocols
python scripts/audit_protocol_governance.py
```

For local read-only browsing, run `view-protocols.bat` from the repository root.
The Chinese portal at `http://127.0.0.1:8001/` exposes this product's locked
snapshot. Follow its GitHub link to inspect or modify the unique protocol source.
