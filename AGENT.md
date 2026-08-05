# CartridgeFlow Engineering Guide

## Product Boundary

`PLAN.md` and `PRODUCT_EXPERIENCE_ARCHITECTURE.md` are the current product
decisions. CartridgeFlow has two same-origin layers backed by one FastAPI
application:

- `/studio` and `/projects/{project_id}/studio`: the Intent Layer, containing
  direction discovery and reviewed semantic composition;
- `/capabilities`: the Capability Layer workshop for executable implementation,
  verification and immutable publication.

The Intent Studio never exposes Root Flow topology, executor/tool bindings, permissions,
runtime controls, debug events or tuning versions. The capability workshop
builds complete internal Flows and publishes immutable reusable releases. A
A project reaches Capability Layer facts only through strict recursive package
materialization. Production execution and independent package tests belong in
`demos/`.

The two surfaces share project identity, the capability registry and backend
facts. Do not couple separate frontend ports or duplicate backend state. Do not
restore retired generic or persona-named frontend projections.

Business-specific behavior belongs in a capability cartridge and its DLC. The
Base owns cross-cartridge contracts, execution safety, storage boundaries and
extension hosting. API keys, user configuration, runs, artifacts and generated
output belong under ignored `.data/`, never in the repository.

## Core Chain

```text
Creator semantic recipe
  -> exact trusted capability releases
  -> recursive dependency closure
  -> deterministic self-contained CF-FARP@1.7 Root Flow
  -> signed CF-CRE package
  -> demos/runtime consumer
```

Missing capabilities remain unresolved semantic nodes. They may block package
publication, but must not block discovery, editing, persistence or review of
the user's intent. Publishing a matching workspace capability re-resolves the
same node identity; it never rebuilds the user's recipe.

Flow authoring is source-first. The workshop writes manifest and Root Flow
facts, the analyzer derives engineering relations, and the runner consumes only
validated executable contracts.

## Protocol Rules

`protocol/catalog/release_manifest.json` is the release source of truth.
Creator recursive packaging uses `CF-FARP@1.7` hosted with `CF-TUNING@1.5`.
These releases define semantic recipes, immutable complete-Flow capabilities,
typed public ports, exact dependencies, trust scope and provenance. Generic
Developer Flows continue to follow the catalog's default FARP version.

Do not rewrite a published protocol release. A semantics-preserving release
gets an independent version directory; a semantic change also gets an adapter,
implementation, tests and evidence. Run the governance audit after every
protocol change. Never add domain capabilities such as RSS to Base; ship them
as package-owned DLC.

## Validation

```powershell
python scripts/run_conformance.py --quiet
python scripts/audit_protocol_governance.py
npm --prefix src/intent-studio run build
npm --prefix src/intent-studio run test
npm --prefix src/capability-workshop run build
npm --prefix src/capability-workshop run test
python -m compileall -q src scripts
trufflehog filesystem . --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update --exclude-paths=config/trufflehog-filesystem-exclude.txt
trufflehog git file://. --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update
```

Browser acceptance must cover both desktop and mobile: unresolved Creator node,
workshop handoff, Flow editing, capability publication, in-place re-resolution,
Creator review and final package download. Check browser console errors.

## Ownership Map

- `src/backend/`: same-origin routes and request/response validation.
- `src/core/cartridge/`: package validation, loading and run lifecycle.
- `src/core/lab/`: technical Flow authoring, analysis and node execution.
- `src/core/protocol/`: release, compatibility and capability contracts.
- `src/core/runtime/`: checkpoints, recovery, errors and runtime adapters.
- `src/core/studio/`: semantic sessions, capability registry and packaging.
- `src/intent-studio/`: direction discovery and semantic composition only.
- `src/capability-workshop/`: executable capability design, verification and publication only.
- `demos/`: capability examples and independent runtime/test bench.

When maintained files move, update `docs/development/FILE_INVENTORY.md`.
