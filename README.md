# CartridgeFlow

CartridgeFlow turns an open-ended idea into a reviewed semantic recipe and a
signed, portable application cartridge. A cartridge can also be a reusable
capability inside another cartridge, so uncommon requirements can be built once
and composed recursively instead of being rejected or hard-coded into Base.

## Start

Requires Python 3, Node.js 20.19 or later, and npm on `PATH`.

```powershell
git submodule update --init protocol-source
powershell -ExecutionPolicy Bypass -File scripts/bootstrap.ps1
run.bat
```

One FastAPI process serves both authoring surfaces on one origin:

- Intent Studio: `http://127.0.0.1:8765/studio`
- Capability Workshop: `http://127.0.0.1:8765/capabilities`

`run.bat` clears only a stale CartridgeFlow listener on port 8765, builds both
bundles and starts the shared backend. Drafts, capability releases and generated
packages live under ignored `.data/`. Set `CARTRIDGEFLOW_DATA_ROOT` before
startup to relocate this directory.

## Product Flow

```text
idea -> semantic canvas -> trusted capability binding
     -> recursive package -> demos/runtime verification
```

If no implementation matches a semantic node, the Intent Studio preserves the node as a
capability gap. An advanced user can open the workshop, build and publish a
complete Flow as a workspace-trusted capability, then return to the same
Intent Studio node for automatic re-resolution and review. The Intent Layer
contains no run or implementation configuration UI; package publication is its
only handoff into executable facts.

## Verify

```powershell
python scripts/run_conformance.py --quiet
python scripts/audit_protocol_governance.py
npm --prefix src/intent-studio run build
npm --prefix src/intent-studio run test
npm --prefix src/capability-workshop run build
npm --prefix src/capability-workshop run test
trufflehog filesystem . --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update --exclude-paths=config/trufflehog-filesystem-exclude.txt
trufflehog git file://. --results=verified --exclude-detectors=Lob --fail --fail-on-scan-errors --no-update
```

The repository does not integrate Lob. Its live verifier classifies ordinary
Python `test_*` identifiers as verified Lob environment names, so that detector
is explicitly excluded. Remove the exclusion before introducing any Lob
integration; all other detectors remain enabled.

## Repository

- `src/backend/`: shared HTTP application and API routes.
- `src/core/`: cartridge, runtime, protocol, lab and studio logic.
- `src/intent-studio/`: direction discovery and semantic composition.
- `src/capability-workshop/`: executable capability design, verification and publication.
- `protocol-source/`: embedded Git submodule containing the authoritative SQLite knowledge base from [cartridgeflow-protocols](https://github.com/Holosukiyaa/cartridgeflow-protocols).
- `config/protocol/`: pinned read-only `protocol-registry.sqlite` published from the embedded authority.
- `demos/capabilities/`: package-owned capability examples such as RSS.
- `demos/runtime-developer-toolkit/`: independent package test bench.
- `scripts/`: bootstrap, launch, verification and test tools.

Read `AGENT.md` for engineering boundaries and
`PRODUCT_EXPERIENCE_ARCHITECTURE.md` for the product contract.

## Protocol Library

Open the Chinese, local read-only knowledge browser:

```powershell
view-protocols.bat
```

The first launch creates an isolated viewer under ignored `.tools/` and installs
its pinned Datasette dependencies. The browser binds only to `127.0.0.1:8001`
and opens a Chinese portal for both databases: the authoritative protocol
original and the product governance snapshot. The product snapshot also makes
the approved committed `config/` documentation, defaults and safe templates
readable and searchable. Runtime state under `.data/` is never included. Stop
the viewer with `Ctrl+C`.
