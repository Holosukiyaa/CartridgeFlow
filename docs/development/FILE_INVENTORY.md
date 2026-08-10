# CartridgeFlow File Inventory

This is the maintained ownership index for current source. Generated output,
dependencies, caches and `.data/` are deliberately excluded.

| Area | Owner | Entry points |
|---|---|---|
| Product decisions | Repository root | `README.md`, `AGENT.md`, `PLAN.md`, `PRODUCT_EXPERIENCE_ARCHITECTURE.md`, `run.bat` |
| Shared backend | `src/backend/` | `main.py`, `api_models.py` |
| Cartridge runtime | `src/core/cartridge/` | `registry.py`, `runner.py`, `root_flow.py`, `validator.py` |
| Technical Flow authoring | `src/core/lab/` | `dev_flow.py`, `flow_analyzer.py`, `node_executor.py` |
| Protocol | `protocol-source/`, `config/protocol/`, `config/protocol-viewer/`, `src/core/protocol/`, `scripts/` | `protocol-source.sqlite`, `protocol-registry.sqlite`, `protocol-registry.lock.json`, `datasette.json`, `templates/`, `requirements.txt`, `view-protocols.bat`, `launch_protocol_viewer.py`, `artifact_store.py`, `release_catalog.py`, `governance_registry.py`, `compatibility.py` |
| Runtime | `src/core/runtime/`, `src/core/orchestration/` | `manager.py`, `execution_plan.py` |
| Extensions | `src/core/extensions/` | `descriptor.py`, `registry.py`, `worker_client.py` |
| Intent and capability services | `src/core/studio/`, `src/core/llm/` | `authoring_service.py`, `capability_cartridges.py`, `creator_runtime_bridge.py`, `creator_flow_skill.py`, `creator_node_skill.py` |
| Intent Studio | `src/intent-studio/src/` | `main.tsx`, `App.tsx`, `api.ts`, `pages/intent-studio/IntentStudio.tsx`, `IntentCanvas.tsx`, `styles/intent-studio.css` |
| Capability Workshop | `src/capability-workshop/src/` | `main.tsx`, `api.ts`, `styles.css` |
| Capability examples | `demos/capabilities/` | `rss-reader/manifest.json`, `rss-reader/root.flow.json`, package-owned DLC |
| Independent package test bench | `demos/runtime-developer-toolkit/` | `README.md`, `guide/`, `demo/`, `samples/` |
| Tests | `scripts/tests/` | `api/`, `browser/`, `conformance/`, `integration/`, `studio/`, `runtime/` |
| Automation | `scripts/` | `bootstrap.ps1`, `launch.py`, `run_conformance.py`, `audit_protocol_governance.py`, `build_protocol_registry.py`, `update_protocol_registry.py` |
| Secret-scan policy | `config/` | `trufflehog-filesystem-exclude.txt` |
| Flow authoring skill | `docs/development/skills/cartridgeflow-flow-author/` | `SKILL.md`, references and validators |
| Protocol upgrade skill | `docs/development/skills/cartridgeflow-protocol-upgrader/` | `SKILL.md`, upgrade checklist |

The retired standalone creator projection, completed worker
handoffs, superseded visual baselines and dated cleanup reports are not
maintained. Product decisions live in the root documents; the Intent Layer is
`src/intent-studio/` and the Capability Layer is `src/capability-workshop/`.

When a durable source file moves, update this index in the same change.
