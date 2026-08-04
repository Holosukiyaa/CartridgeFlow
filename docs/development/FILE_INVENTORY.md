# CartridgeFlow File Inventory

This is a maintained ownership index, not a generated claim that a manually
curated list is the complete repository tree. The authoritative full tree and
cleanup disposition live in `PROJECT_CLEANUP_AUDIT_2026-07-31.md`.

| Area | Owner | Entry points |
|---|---|---|
| Product | Repository root | `README.md`, `AGENT.md`, `PLAN.md`, `PRODUCT_EXPERIENCE_ARCHITECTURE.md`, `VERSION`, `run.bat` |
| Backend | `src/backend/` | `main.py` |
| Cartridge runtime | `src/core/cartridge/` | `registry.py`, `runner.py`, `root_flow.py`, `validator.py` |
| Authoring | `src/core/lab/` | `dev_flow.py`, `flow_analyzer.py`, `node_executor.py` |
| Protocol | `protocol/`, `src/core/protocol/` | `flow-authoring/1.5/`, `tuning/1.4/`, historical `flow-authoring/1.4/` and `tuning/1.3/`, `trusted_node_recipes.py`, `creator_templates.py`, `release_catalog.py`, `tuning.py`, `compatibility.py` |
| Runtime | `src/core/runtime/`, `src/core/orchestration/` | `manager.py`, `execution_plan.py` |
| Extensions | `src/core/extensions/` | `descriptor.py`, `registry.py`, `worker_client.py` |
| Creator authoring | `src/core/studio/`, `src/core/llm/` | `trusted_node_presets.py`, `authoring_service.py`, `creator_flow_skill.py`, `creator_node_skill.py`, `creator_runtime_bridge.py`, legacy `creator_discovery.py` |
| Creator Studio | `src/creator-studio/src/` | `main.tsx`, `App.tsx`, `App.css`, `api.ts` |
| Historical standalone projections | `src/creator-studio/src/`, `src/developer-console/src/` | retained implementation references; not launched by `run.bat` |
| Unified Creator and Developer frontend | `src/frontend/src/` | `main.tsx`, `App.tsx`, `pages/FlowWorkbench.tsx`, `pages/flow-workbench/CreatorWorkspace.tsx`, `pages/flow-workbench/TrustedNodePanel.tsx`, `pages/flow-workbench/NodeExperiencePanel.tsx` |
| Tests | `scripts/tests/` | `api/`, `browser/`, `conformance/`, `runtime/`, `studio/`, `lab/`, `orchestration/`, `ui/` |
| Automation | `scripts/` | `bootstrap.ps1`, `launch.py`, `run_conformance.py`, `run_node_coverage.py` |
| Flow authoring skill | `docs/development/skills/cartridgeflow-flow-author/` | `SKILL.md`, `references/authoring-checklist.md`, `scripts/preflight_flow.py`, `scripts/validate_authored_cartridge.py` |
| Creator composition skills | `docs/development/skills/` | `compose-creator-flow/SKILL.md`, `refine-creator-node/SKILL.md`, each skill's `agents/openai.yaml` |
| Runtime developer toolkit | `demos/runtime-developer-toolkit/` | `README.md`, `guide/`, `demo/`, `samples/` |
| Authoring/runtime handoff boundary | `docs/development/` | `AUTHORING_RUNTIME_HANDOFF_BOUNDARY.md` |
| Trusted-node audit | `docs/development/` | `CREATOR_TRUSTED_NODE_GAP_MAP.md` |

Generated output, dependencies, caches, user data, and temporary files are not
enumerated. They must remain outside source ownership and outside Git.

When a durable source file moves, update this index if its ownership or entry
point changes, then refresh the cleanup audit file tree.
