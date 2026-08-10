# Compiled Protocol Registry

`protocol-registry.sqlite` is the read-only federated protocol knowledge base
consumed by this product. It contains complete artifacts and searchable sections
for both `current` and `temp-runtime`. Runtime reads default to `current`; the
second line is present for governance and comparison, never implicit merging.

`protocol-registry.lock.json` pins the authoritative `protocol-source.sqlite`
to one full Git commit, its source database SHA-256 and logical digest. It also
pins the published product database SHA-256.

Protocol originals live at:

```text
https://github.com/Holosukiyaa/cartridgeflow-protocols
```

Do not edit this product database directly. Update the authoritative source
database with `scripts/protocol_db.py`, verify it, commit and push it, then
publish from the CartridgeFlow repository:

```powershell
python scripts/update_protocol_registry.py
python scripts/audit_protocol_governance.py
```
