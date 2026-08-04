# CartridgeFlow

CartridgeFlow is a local Creator product for turning an open-ended idea into a
reviewed dynamic recipe and a signed portable package. It ships one FastAPI
application and one Creator-only React canvas. Engineering materialization is
hidden behind the strict package boundary; package execution and testing belong
to `demos/`.

## Start

Requires Python 3, Node.js 20.19 or later, and npm on `PATH`.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
python scripts/launch.py
```

Creator opens at `http://127.0.0.1:5173`. User drafts, generated packages,
and temporary files live under `.data/` by default. Set
`CARTRIDGEFLOW_DATA_ROOT` before process startup to relocate that data root.
Relative values are resolved from the repository root; use an absolute path to
place runtime data elsewhere on the machine.

The repository has three independent version dimensions: `VERSION` is the
CartridgeFlow product release, `src/frontend/package.json` versions the private
frontend bundle, and `config/base/BASE_IMPLEMENTATION.json` versions the Base
implementation and its protocol support evidence.

## Verify

```powershell
python scripts/run_conformance.py
python scripts/audit_protocol_governance.py
npm --prefix src/frontend run build
```

## Repository

- `src/backend/`: HTTP application and API routes.
- `src/core/`: cartridge, runtime, protocol, lab, extension, and resource logic.
- `src/frontend/`: Creator-only React canvas.
- `protocol/`: versioned Base, Flow Authoring, and Release Envelope releases.
- `config/`: committed Base declarations, defaults, and safe templates.
- `scripts/`: bootstrap, launch, verification, and test tools.

Read [AGENT.md](AGENT.md) for ownership rules and
`docs/development/PROJECT_CLEANUP_AUDIT_2026-07-31.md` for the current cleanup
audit and full repository map.
