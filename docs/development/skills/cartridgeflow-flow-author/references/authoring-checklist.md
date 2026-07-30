# Flow Authoring Checklist

## New Development Cartridge

Create through `POST /api/lab/flows` or the workbench's **新建卡带** action. The manager creates `manifest.json`, `root.flow.json`, `assets/registry.json`, and `assets/components.json` together.

Use a `dev.` cartridge ID, a Chinese business name, and a one-sentence Chinese description by default. Use English only for code symbols, protocol values, field keys, paths, and external tool parameters. Do not place secrets, generated output, or local credentials in the cartridge.

## Typed v0.9 Process Node

Use this shape for every process node:

```json
{
  "type": "process",
  "kind": "mcp_read",
  "executor": "mcp",
  "effect": "read_only",
  "title": "整理新闻候选",
  "display_name": "整理新闻候选",
  "action": "mcp_read",
  "inputs": {
    "request": {
      "required": true,
      "schema": { "type": "object" },
      "binding": { "source": "constant", "value": {} }
    }
  },
  "outputs": {
    "result": {
      "schema": { "type": "object" },
      "target": { "type": "store", "key": "result" }
    }
  },
  "scope": "sub_flow",
  "next": "next_node"
}
```

For data from another node, use:

```json
"binding": { "source": "node_output", "node_id": "previous_node", "output": "result" }
```

Do not use legacy process-node `input`, `optional_input`, or `output` fields in v0.9.

## MCP and DLC

- Declare every tool in `manifest.mcp_tools` before referencing it in `allowed_tools`.
- Use `cartridge_dlc` plus `portable_dlc` only when the source belongs to this cartridge.
- DLC source must be package-relative, parse as `cartridgeflow.mcp_python.v1`, and match its descriptor digest.
- Use the business node title for the user interface. Internal `node_id` and manifest tool IDs support validation only.

## Mandatory Checks

Run the skill preflight after editing a cartridge. Then run the smallest relevant test set; use full conformance for shared contracts, protocol changes, or release work.

```powershell
python -B scripts/run_conformance.py --quiet
npm --prefix src/frontend run build
```

Resolve analyzer blockers instead of bypassing a contract. Warnings are still design evidence and should be explained at handoff.
