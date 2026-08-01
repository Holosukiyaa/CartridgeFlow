# Flow Authoring Checklist
## New Development Cartridge

Create through `POST /api/lab/flows` or the workbench's **新建卡带** action. The manager creates `manifest.json`, `root.flow.json`, `assets/registry.json`, and `assets/components.json` together.

Use a `dev.` cartridge ID, a Chinese business name, and a one-sentence Chinese description by default. Use English only for code symbols, protocol values, field keys, paths, and external tool parameters. Do not place secrets, generated output, or local credentials in the cartridge.

## Typed CF-FARP@1.0 Process Node

Use this shape for every process node:

```json
{
  "type": "process",
  "kind": "mcp_read",
  "executor": "mcp",
  "effect": "read_only",
  "title": "读取外部资料",
  "display_name": "读取外部资料",
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
  "scope": "sub_flow"
}
```

For data from another node, use:

```json
"binding": { "source": "node_output", "node_id": "previous_node", "output": "result" }
```

Connect process nodes only through `execution_plan.edges`; do not add legacy `next`, `control_edges`, `input`, `optional_input`, or `output` fields. An output target must be nested under its output port as shown above. Sibling `store` or `artifact` fields are not runtime output bindings.

## Runtime Configuration And Failure Path

- For a model role resolved from the user's local binding, declare `"model": "configured-locally"`. `"user-configured"` is explanatory prose, not a recognized runtime sentinel, and will override an otherwise valid binding.
- Before the first run, inspect `GET /api/lab/flows/<cartridge-id>/resource-catalog`: every required model role and node binding must resolve to an enabled, usable provider. Do not claim a Flow is runnable from a manifest-only check.
- A structured `llm_prompt` executor receives one request input unless its implementation explicitly supports more. Combine date, topic, source data, and instructions into one typed object before the LLM node.
- Exercise a safe malformed input after the happy path. Verify that the declared failure edge reaches a terminal state, that the terminal does not attempt an action dispatch, and that the run retains only the original node error.
- Verify on a running backend that the process loaded the current `src/` code; `uvicorn` has no `--reload`, so a stale process reports `ACTION_EXECUTOR_MISSING` for newly registered node actions. Restart it after editing `src/`.

## LLM Node Runtime Tuning

Reality check from end-to-end runs with reasoning models (e.g. `deepseek-v4-flash`): the model spends most of the token budget on reasoning before any answer text, and each call routinely takes one to two minutes. A Flow that validates is still not runnable until each `llm_prompt` node is tuned.

- Set `llm_options.max_tokens` high — reasoning models with big contexts routinely burn the whole budget on reasoning. Give `20000` unless the prompt is tiny; `6000`–`8000` still fails intermittently on long prompts (observed `finish_reason=length` → `PROVIDER_EMPTY_RESPONSE` even at `8000`). A small budget (e.g. `1400`) reliably produces empty content. The same node can pass earlier with the default budget and fail once `llm_options` caps it, so retest after adding the option.
- Set `llm_options.timeout_seconds` above the slowest observed inference (`150` is safe). A `45`-second budget yields `APITimeoutError` → `PROVIDER_UNAVAILABLE` on slow reasoning calls.
- Keep the node's `prompt` output shape identical to its `decision_contract.consume` path (e.g. `payload.recommendation`, not `payload.decision.recommendation`). Include one exact JSON example, forbid Markdown and non-ASCII quotes, and cap output length in the prompt.
- Model JSON drift still happens occasionally: `DECISION_ENVELOPE_INVALID` / `decision_envelope_parse_failed` reach the declared `failure` edge. That fail-closed behavior is correct; do not weaken validation to make a run pass.

## Execution Plan Integrity

The canvas and the runner both derive from `execution_plan.edges`; a missing edge breaks the layout and can stop the run. Check after every edit that:

- The main chain is continuous: every non-terminal state that has a non-failure incoming edge also has a non-failure outgoing edge. This includes the approval path of interaction nodes (`confirm_checkpoint` → next state is a `sequence` edge that must survive saves).
- Every state that may fail declares a `failure` edge to a terminal state.
- `validate_authored_cartridge.py` reports `FLOW_SUCCESSOR_EDGE_MISSING` when the chain breaks (it stays a warning because a state with no incoming edge may legally end the flow — verify the flagged state really is the intended end).
- When adding or reconnecting nodes through the workbench, re-read the saved `execution_plan.edges` afterwards: the edge save is full-replacement, so a canvas that briefly missed an edge can persist the loss.

## LLM Node Template (write it right the first time)

One `llm_prompt` decision node, shaped so the options, contract, and prompt agree from the first write:

```json
{
  "type": "process",
  "kind": "decision",
  "executor": "llm",
  "effect": "none",
  "action": "llm_prompt",
  "title": "评估候选方案",
  "display_name": "评估候选方案",
  "model_role": "analyst",
  "llm_options": { "timeout_seconds": 150, "max_tokens": 20000 },
  "output_contract": "decision_envelope.v1",
  "decision_contract": {
    "schema": "decision_envelope.v1",
    "allowed_statuses": ["resolved", "blocked"],
    "consume": { "mode": "payload_path", "path": "payload.recommendation", "as": "selected_option", "required": true, "on_missing": "fail_closed" }
  },
  "inputs": {
    "request": { "required": true, "schema": { "type": "object" },
                 "binding": { "source": "node_output", "node_id": "prepare_request", "output": "request_context" } }
  },
  "outputs": {
    "evaluation_decision": { "schema": { "type": "object" }, "target": { "type": "store", "key": "evaluation_decision" } }
  },
  "system_prompt": "你是谨慎的业务分析员，只能依据输入材料作出结论。",
  "prompt": "评估输入中的候选方案。只返回一个 JSON 对象（decision_envelope.v1），结构如下：{\"schema\":\"decision_envelope.v1\",\"status\":\"resolved\",\"summary\":\"一句话\",\"payload\":{\"recommendation\":{\"id\":\"option-id\",\"reason\":\"依据\"}}}\n要求：不使用 Markdown；使用 ASCII 双引号；不虚构输入中不存在的事实；总输出低于 1200 tokens。"
}
```

Notes from a verified run (reasoning model): `max_tokens` below ~6000 yields `PROVIDER_EMPTY_RESPONSE` (`finish_reason=length`) because reasoning consumes the budget; `8000` can still fail on long prompts — prefer `20000`; `timeout_seconds` below ~90 yields `APITimeoutError` → `PROVIDER_UNAVAILABLE`. The prompt's output shape must match `consume.path` + `as` (`payload.recommendation` + `selected_option` above). Model drift still happens; keep the `failure` edge.

Never label an LLM node as `transform` or `validation`, and never let it write a file directly. The protocol requires `kind=decision`, `executor=llm`, `effect=none`, `output_contract=decision_envelope.v1`, and explicit consume. Add a following deterministic `effect=writes_artifacts` node when the business result must become a file. This split prevents an empty provider response from becoming a zero-byte Artifact with a false-green run.

## Date Input Default

A run input that means "today" uses `runtime_default.current_date` (timezone-aware):

```json
{
  "type": "process",
  "action": "collect_inputs",
  "params": {
    "fields": ["run_date", "request_context"],
    "output": "run_request",
    "defaults": { "run_date": { "type": "current_date", "timezone": "Asia/Shanghai" } }
  }
}
```

The frontend renders the field as a date picker and the runner fills the date when the caller omits it.

## Real Delivery Closure

Drive one end-to-end run before handoff: `POST /api/cartridge-runs` with real inputs, poll `GET /api/cartridge-runs/{run_id}`, and approve `paused_waiting_user` interactions through the answer API. A completed run plus a failing-path run are the minimum execution evidence, but `status=completed` only proves the graph reached a terminal state.

Before claiming delivery, verify all of these facts:

- `run.errors` is empty and `run.data_chain.passed=true`.
- `GET /api/cartridge-runs/<run-id>/delivery` exists and reports `status=delivered`.
- `delivery.primary_output` equals `manifest.delivery.primary_output`. A Store-backed primary has a non-empty `delivery.result`; an Artifact-backed primary has a matching `primary_artifact.artifact_id`.
- Every declared delivered Artifact resolves inside `.data/runtime/runs/<run-id>/artifacts/` and has non-zero bytes. An Artifact record is not evidence that the file exists.
- Every declared Artifact URL returns real bytes. Browser preview is secondary; the workbench's **打开产物文件夹** action uses a run-scoped host endpoint because a browser cannot reliably reveal native files.
- Empty model content fails at the source with `PROVIDER_EMPTY_RESPONSE`; it must never be converted into an empty string, empty Artifact, or successful Delivery.
- Restart the backend after any `src/` edit before gathering evidence. A stale non-reloading process can make correct source appear broken or old source appear fixed.
- Keep domain-specific quality checks in the cartridge's own tests or DLC. This generic skill checks protocol, execution, Artifact existence, and Delivery reachability only.

Run the executable handoff check against the exact final Run:

```powershell
python docs/development/skills/cartridgeflow-flow-author/scripts/validate_authored_cartridge.py --repo . --package .data/user/dev_cartridges/<cartridge-id> --run-id <run-id> --api-url http://127.0.0.1:8765
```

## MCP and DLC

- Declare every tool in `manifest.mcp_tools` before referencing it in `allowed_tools`.
- Use `cartridge_dlc` plus `portable_dlc` only when the source belongs to this cartridge.
- DLC source must be package-relative, parse as `cartridgeflow.mcp_python.v1`, and match its descriptor digest.
- Use the business node title for the user interface. Internal `node_id` and manifest tool IDs support validation only.

## Mandatory Checks

Run both skill checks after editing a cartridge. `preflight_flow.py` verifies package and Flow contracts; `validate_authored_cartridge.py` additionally verifies the final user-visible text, text assets, resource catalog, and local model binding. A card with `???`, empty visible labels, a blocked provider, or a blocked required resource is not ready to hand off.

```powershell
python docs/development/skills/cartridgeflow-flow-author/scripts/preflight_flow.py --repo . --package .data/user/dev_cartridges/<cartridge-id>
python docs/development/skills/cartridgeflow-flow-author/scripts/validate_authored_cartridge.py --repo . --package .data/user/dev_cartridges/<cartridge-id>
```

```powershell
python -B scripts/run_conformance.py --quiet
npm --prefix src/frontend run build
```

Resolve analyzer blockers instead of bypassing a contract. Warnings are still design evidence and should be explained at handoff.
