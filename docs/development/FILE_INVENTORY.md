# CartridgeFlow File Inventory

This is a maintained ownership index, not a generated claim that a manually
curated list is the complete repository tree. The authoritative full tree and
cleanup disposition live in `PROJECT_CLEANUP_AUDIT_2026-07-31.md`.

| Area | Owner | Entry points |
|---|---|---|
| Product | Repository root | `README.md`, `AGENT.md`, `VERSION`, `run.bat` |
| Backend | `src/backend/` | `main.py` |
| Cartridge runtime | `src/core/cartridge/` | `registry.py`, `runner.py`, `root_flow.py`, `validator.py` |
| Authoring | `src/core/lab/` | `dev_flow.py`, `flow_analyzer.py`, `node_executor.py` |
| Protocol | `protocol/`, `src/core/protocol/` | `catalog/release_manifest.json`, `release_catalog.py`, `compatibility.py` |
| Runtime | `src/core/runtime/`, `src/core/orchestration/` | `manager.py`, `execution_plan.py` |
| Extensions | `src/core/extensions/` | `descriptor.py`, `registry.py`, `worker_client.py` |
| Local resources | `src/core/studio/` | `resource_catalog.py`, `resource_resolver.py` |
| Frontend | `src/frontend/src/` | `main.tsx`, `App.tsx`, `pages/FlowWorkbench.tsx` |
| Tests | `scripts/tests/` | `api/`, `conformance/`, `runtime/`, `studio/`, `lab/`, `orchestration/`, `ui/` |
| Automation | `scripts/` | `bootstrap.ps1`, `launch.py`, `run_conformance.py`, `run_node_coverage.py` |

Generated output, dependencies, caches, user data, and temporary files are not
enumerated. They must remain outside source ownership and outside Git.

When a durable source file moves, update this index if its ownership or entry
point changes, then refresh the cleanup audit file tree.
