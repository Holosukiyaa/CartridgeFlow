# CartridgeFlow File Inventory

This is the maintained ownership index for current source. Generated output,
dependencies, caches and `.data/` are deliberately excluded.

| Area | Owner | Entry points |
|---|---|---|
| Product decisions | Repository root | `README.md`, `AGENT.md`, `PLAN.md`, `PRODUCT_EXPERIENCE_ARCHITECTURE.md`, `run.bat` |
| Shared backend | `src/backend/` | `main.py`, `api_models.py` |
| Cartridge runtime | `src/core/cartridge/` | `registry.py`, `runner.py`, `root_flow.py`, `validator.py` |
| Technical Flow authoring | `src/core/lab/` | `dev_flow.py`, `flow_analyzer.py`, `node_executor.py` |
| Protocol | `protocol/`, `src/core/protocol/` | `flow-authoring/1.7/`, `tuning/1.5/`, `capability_cartridges.py`, `release_catalog.py`, `compatibility.py` |
| Runtime | `src/core/runtime/`, `src/core/orchestration/` | `manager.py`, `execution_plan.py` |
| Extensions | `src/core/extensions/` | `descriptor.py`, `registry.py`, `worker_client.py` |
| Creator and capability services | `src/core/studio/`, `src/core/llm/` | `authoring_service.py`, `capability_cartridges.py`, `creator_runtime_bridge.py`, `creator_flow_skill.py`, `creator_node_skill.py` |
| Creator frontend | `src/frontend/src/` | `main.tsx`, `App.tsx`, `api.ts`, `pages/flow-workbench/CreatorStudio.tsx`, `CreatorCanvas.tsx`, `styles/creator.css` |
| Capability workshop | `src/developer-console/src/` | `main.tsx`, `api.ts`, `styles.css` |
| Capability examples | `demos/capabilities/` | `rss-reader/manifest.json`, `rss-reader/root.flow.json`, package-owned DLC |
| Independent package test bench | `demos/runtime-developer-toolkit/` | `README.md`, `guide/`, `demo/`, `samples/` |
| Tests | `scripts/tests/` | `api/`, `conformance/`, `integration/`, `studio/`, `runtime/`, `ui/` |
| Automation | `scripts/` | `bootstrap.ps1`, `launch.py`, `run_conformance.py`, `audit_protocol_governance.py` |
| Secret-scan policy | `config/` | `trufflehog-filesystem-exclude.txt` |
| Flow authoring skill | `docs/development/skills/cartridgeflow-flow-author/` | `SKILL.md`, references and validators |
| Creator composition skills | `docs/development/skills/` | `compose-creator-flow/`, `refine-creator-node/` |

The retired standalone `src/creator-studio/` projection is not maintained. The
Creator product is `src/frontend/`; the workshop is `src/developer-console/`.

When a durable source file moves, update this index in the same change.
