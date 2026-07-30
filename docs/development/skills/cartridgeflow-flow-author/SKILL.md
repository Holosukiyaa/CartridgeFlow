---
name: cartridgeflow-flow-author
description: Create, extend, or repair editable CartridgeFlow development cartridges and root flows. Use when a user asks Codex to turn a business goal into a CartridgeFlow Flow, add process nodes, configure typed data contracts, bind models or MCP/DLC tools, or make a Flow pass v0.9 validation without repeated trial-and-error.
---

# CartridgeFlow Flow Author

Create the smallest executable Flow that satisfies the user's business goal and the current CF-FARP contract. Prefer Chinese titles, display names, cartridge names, and user-facing descriptions; retain original text only for code symbols, protocol values, field keys, paths, and external tool parameters.

## Required Reads

Read before editing:

- `AGENT.md`
- `references/authoring-checklist.md`
- `protocol/catalog/release_manifest.json`

Read `docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.9.md` when creating a typed v0.9 Flow or a DLC MCP tool.

## Workflow

1. Run the authoring simulation before changing a user cartridge. Fix the workbench service when this fails; never turn a known platform error into a user instruction.
2. Identify whether the request creates a new development cartridge, changes an existing business flow, or adds a resource-backed node.
3. For a new cartridge, use the workbench/API creation path so the asset registry and component files are generated. Do not hand-create a package skeleton.
4. Model business steps as `states` and typed `control_edges`. Keep system start and terminal nodes locked.
5. For every `type: process` node in a v0.9 Flow, declare `inputs` and `outputs`; every input needs `required` and exactly one `schema` or `schema_ref`; every output needs a schema and a `store` or `artifact` target.
6. Bind a tool by its manifest tool ID in `allowed_tools`. For a transparent DLC MCP tool, keep the user-facing business node separate from its internal source model; do not add an ID-only business node.
7. Add models, permissions, failure policies, replay policies, and delivery fields only when the selected node effect requires them. Never invent a successful fallback for a missing external capability.
8. Run package preflight after each meaningful edit. Resolve blockers before adding more nodes.
9. Run the relevant build and conformance commands before handing off.

## Workbench Simulation

Run this first against the active local workbench. It confirms that the user-facing frontend is reachable and that the backend can create a temporary cartridge, create a Chinese-titled business node, save layout, validate, check compatibility, read the resource catalog, and remove test data.

```powershell
powershell -ExecutionPolicy Bypass -File docs/development/skills/cartridgeflow-flow-author/scripts/simulate_authoring.ps1
```

Do not substitute screenshots for this interface. The endpoint returns a structured trace for each workbench action and fails on cleanup failure.

## Package Preflight

Run from the repository root:

```powershell
python docs/development/skills/cartridgeflow-flow-author/scripts/preflight_flow.py --repo . --package .data/user/dev_cartridges/<cartridge-id>
```

The script validates the manifest, typed flow analysis, and resource catalog for the cartridge being edited. Read its JSON output and fix the reported source path or node contract; do not weaken the validator.

When this skill is installed outside the repository, point `--repo` at the CartridgeFlow checkout and use the installed script path.

## Completion

Report the business nodes created, declared resources, validation result, and any external configuration still required. Read `references/authoring-checklist.md` for field patterns and validation commands.
