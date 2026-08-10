# Compiled Protocol Registry

`protocol-registry.sqlite` is the read-only federated protocol knowledge base
consumed by this product. It contains complete artifacts and searchable sections
for both `current` and `temp-runtime`. Runtime reads default to `current`; the
second line is present for governance and comparison, never implicit merging.

`protocol-registry.lock.json` pins both source paths to one full Git commit,
plus the logical registry digest and database SHA-256.

Protocol originals live at:

```text
https://github.com/Holosukiyaa/cartridgeflow-protocols
```

Do not edit the database directly. Update the protocol repository, commit and
push it, then rebuild from the CartridgeFlow repository:

```powershell
python scripts/update_protocol_registry.py
python scripts/audit_protocol_governance.py
```
