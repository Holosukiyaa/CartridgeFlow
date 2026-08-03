# CartridgeFlow Engineering Guide

## Product Boundary

The frozen product and delivery baseline is `PLAN.md` revision
`creator-ai-authoring-2026-08-r1`. CartridgeFlow owns creator authoring and a
separate developer console; the runtime product owns production execution and
receives only signed cartridge packages. Do not add production run, queue,
history, artifact-delivery, or runtime-interaction UI to Creator Studio.

The current v0.7 implementation is still a single local development workbench.
Its backend entry point is `src/backend/main.py`; `src/frontend/src/App.tsx` is
the frontend entry. Existing runtime routes and modules remain compatibility
implementation until an explicitly scoped delivery changes them; they do not
define the Creator Studio product surface.

Business-specific behavior belongs in a cartridge or its DLC. The Base owns
cross-cartridge contracts, execution safety, storage boundaries, and extension
hosting. Never put API keys, user configuration, runs, artifacts, or generated
output into the repository; they belong under `.data/`.

## Core Chain

```text
React workbench -> FastAPI routes -> CartridgeRegistry -> compatibility check
-> CartridgeRunner -> RootFlowEngine / node executor -> tools, models, DLC
-> run events, checkpoints, artifacts, and delivery
```

Flow authoring is source-first. The workbench writes manifest and root-flow
facts, the analyzer derives engineering relations, and the runner only consumes
validated executable contracts.

## Protocol Rules

`protocol/catalog/release_manifest.json` is the source of truth for release
lifecycle, default flow version, release snapshots, runtime adapters, and
features. Base support is declared by
`config/base/BASE_IMPLEMENTATION.json.supported_protocol_adapters`; exact
`supported_protocols` entries are historical compatibility declarations.
Trusted internal protocols additionally require an exact host declaration in
the CF-FARP release and a matching `supported_subprotocols` Base adapter. The
current `CF-TUNING@1.0` owns node-local tuning revisions and recipe releases;
it never owns Root Flow topology or executable code.

Do not rewrite a published protocol release. A semantics-preserving new release
gets an independent version directory and may reuse its runtime adapter. A
semantic change gets a new adapter, implementation, tests, and Base evidence.
Run `python scripts/audit_protocol_governance.py` after any protocol change.

## Validation

```powershell
python scripts/run_conformance.py --quiet
npm --prefix src/frontend run build
python -m compileall -q src scripts
```

The conformance entry point covers conformance, runtime, studio, LLM, API, Lab,
orchestration, hygiene, and historical compatibility tests. UI assertions are
kept under `scripts/tests/ui/` and run against the frontend build when their
browser prerequisites are available.

## Ownership Map

- `src/backend/`: HTTP route composition and request/response validation.
- `src/core/cartridge/`: package validation, flow loading, and run lifecycle.
- `src/core/lab/`: authoring, graph projection, analyzer, and node execution.
- `src/core/protocol/`: release registry, compatibility, certification, and contracts.
- `src/core/runtime/`: checkpoints, recovery, errors, and runtime adapters.
- `src/core/studio/`: local resource, portability, package, and release support.
- `src/frontend/src/pages/flow-workbench/`: workbench view components and editors.

When adding, deleting, or moving maintained files, update
`docs/development/FILE_INVENTORY.md` and the current cleanup audit.
