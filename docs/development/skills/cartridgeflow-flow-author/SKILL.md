---
name: cartridgeflow-flow-author
description: Create, extend, or repair editable CartridgeFlow development cartridges and root flows. Use when a user asks Codex to turn a business goal into a CartridgeFlow Flow, add process nodes, configure typed data contracts, bind models or MCP/DLC tools, or make a Flow pass the current executable CF-FARP@1.0 validation without repeated trial-and-error.
metadata:
  version: "2.4.0"
  protocol_alignment:
    label: "cf-farp-1-0-authoring-verified"
    protocol: "CF-FARP@1.0"
    scope: "skill workflow"
    evidence: "workbench simulation, v1 conformance, package preflight, protocol governance audit, and end-to-end run verification"
---

# CartridgeFlow Flow Author

Create the smallest executable Flow that satisfies the user's business goal and the current executable CF-FARP contract. The verified authoring baseline is `CARTRIDGEFLOW-BASE@0.2 + CF-FARP@1.0`. Prefer Chinese titles, display names, cartridge names, and user-facing descriptions; retain original text only for code symbols, protocol values, field keys, paths, and external tool parameters.

## Required Reads

Read before editing:

- `AGENT.md`
- `references/authoring-checklist.md`
- `protocol/catalog/release_manifest.json`
- `protocol/governance/GOVERNANCE.md`

Read `protocol/flow-authoring/1.0/README.md` and its listed normative modules before creating or modifying a v1 Flow or a DLC MCP tool. Read the document path named by the release catalog rather than guessing a version.

## Workflow

1. Run the authoring simulation before changing a user cartridge. Fix the workbench service when this fails; never turn a known platform error into a user instruction. When using an isolated service, pass both `-FrontendUrl` and `-ApiUrl` explicitly.
2. Identify whether the request creates a new development cartridge, changes an existing business flow, or adds a resource-backed node.
3. For a new cartridge, use the workbench/API creation path so the asset registry and component files are generated. Do not hand-create a package skeleton.
4. Model business steps as `states` and `execution_plan.edges`; never create `next`, `control_edges`, action routes, or visual-only executable edges in a v1 Flow. Keep start and terminal nodes locked.
5. For every `type: process` node in a v1 Flow, declare `inputs`, `outputs`, and an explicit `failure` edge when it may fail; every input needs `required` and exactly one `schema` or `schema_ref`; every output needs a schema and a nested `target` object whose `type` is `store` or `artifact`. Keep the main chain continuous: every non-terminal state that has a non-failure incoming edge must also have a non-failure outgoing edge. An interaction node (`confirm_checkpoint`) still needs its approval sequence edge to the next state — a lost edge there broke a real cartridge's canvas and run. The final `validate_authored_cartridge.py` reports this as `FLOW_SUCCESSOR_EDGE_MISSING` (warning; a state with no incoming edge may legally end the flow).
5a. For a `confirm_checkpoint` (人工审核) node, bind what the user actually reviews: its `inputs` must reference **text content already declared as an output contract** (or a store key the upstream wrote), never an artifact id you have not declared in `outputs.target`. The runtime attaches the bound values to the pending question as `review_content` — a binding to an undeclared output silently renders an empty review screen. In practice: upstream `outputs` need a `daily_brief`-style entry with `target: {type: store, key: ...}` before the review node binds it, and the review `binding` should point at the text (store key) rather than an artifact descriptor. `validate_authored_cartridge.py` flags these as `REVIEW_BINDING_UNRESOLVED` (warning) and artifact-bound reviews as `REVIEW_BINDING_ARTIFACT` (info).
5c. For a human review loop (驳回重写循环: draft → review → revise → review …), use `answer_routes` on `params.interaction` combined with a `loop` edge:
    - `answer_routes` (each `{match: {field, equals}, policy, ...}`): the rejected route must set `policy: resume_target_node` + `target_node: <revise-node>` + `clear_store_keys: [approval]` (so the next review pauses again) + `copy_answer_to: <feedback-key>` (so the revise node can read the feedback after the approval key is cleared). The approved route keeps `resume_same_node` and leaves the approval value in the store so the loop edge exits.
    - `loop` edge from the review node: `continue_when: "$approval.feedback"` (non-empty feedback = rejected = keep looping; empty = approved = `exit_to` the packaging node). `$key.field` resolves store values with bool semantics.
    - The revise node must bind its feedback input to the `copy_answer_to` key (e.g. `review_feedback`), not to the cleared approval key.
    - Platform notes (all fixed): `confirm_checkpoint` forwards `answer_routes`/`clear_store_keys`/`copy_answer_to` from `interaction` into the pending resume; `resume_target_node` schedules a fresh ready token for the target (otherwise the token engine skips it); do NOT use `resume_target_node` with `transition_pending` semantics — the paused token would route its success edges (the loop edge) and bypass the target.
5d. For parallel flows (fork/join), remember:
    - `fork` edges share one `fork.id` + source and differ by `fork.branch`; every branch needs its own edge.
    - `join` edges share one `join.id`, target, mode and the FULL `join.branches` set; **each join edge also needs its own `join.branch`** (which branch this edge carries) — forgetting it fails static conformance (`v10_join_contract_invalid`).
    - Manifest `required_capabilities` must name the mode-specific capability: `execution_plan_join_all_contract` (or `join_any`/`join_keyed`) plus `execution_plan_join_runtime` — there is no generic `execution_plan_join_contract` in the base; declaring a missing name blocks run creation (`compatibility_blocked`).
    - A `pass_result` node with `preset_config.items` (comma-separated store keys) + `output_name` merges the branch outputs into one bundle for the join consumer.
5b. Write a real `description` for every node (`params.description`, shown as 节点职责). This is the most user-visible text on the canvas card — it is what tells the user what this machine does. Write it concretely for THIS node (what it consumes, what it produces, why it exists, what the user gains), never template filler like "根据已有信息做出判断". If the node description is generic, rewrite it until it names this node's specific job. A missing description makes the card fall back to generic copy.
6. Bind a tool by its manifest tool ID in `allowed_tools`. For a transparent DLC MCP tool, keep the user-facing business node separate from its internal source model; do not add an ID-only business node. When a `tool_call`/`remote_call` node runs several tools, the runtime writes each tool result to the store under **that tool's own `output` name** (e.g. `rss_theverge`), not under `params.output` — `params.output` is only a fallback for tools without an output name. Downstream nodes must bind those per-tool store keys (one input port per tool), not `params.output`.
7. Verify runtime semantics before the first run. Inspect the field consumer when a value controls runtime behavior; never use prose placeholders as protocol values. A user-bound model role must declare `model: "configured-locally"`, never `"user-configured"`. Confirm the role and node bindings exist in the resource catalog, and that their provider is enabled and usable before calling the Flow runnable.
8. Treat a structured `llm_prompt` node as a single-request consumer unless its executor has been inspected and proven otherwise. Aggregate related business values into one typed object upstream; do not provide several required ports and assume the executor will combine them.
9. Test both paths before handoff: run one valid, non-destructive input and one intentionally invalid, safe input. The latter must traverse the declared failure edge to a terminal node and report only the originating node error; a terminal node must never need an action executor. Interaction nodes (`confirm_checkpoint` and similar) pause the run: answer them through `POST /api/cartridge-runs/{run_id}/pending-interaction/answer` during verification, never by editing the store. Verify the topology cheaply first: run with `test_mode` / `mock` decision envelopes before spending real model calls, then run the real path once for evidence. The `mock_resolved` test envelope always carries the fixed payload `{"decision": ...}` — a node whose `consume.path` is deeper (e.g. `payload.scene_blueprint`) fails `DECISION_CONSUME_FAILED` under mock unless you declare `decision_contract.offline_decision` (a full `decision_envelope.v1` whose payload matches the consume path). Add an `offline_decision` to every LLM node you intend to mock-test.
10. Tune every `llm_prompt` node for the actual model before claiming runnable. On reasoning models (DeepSeek-style), long code/document generation burns 70-90k tokens of hidden reasoning and truncates the visible output (`PROVIDER_EMPTY_RESPONSE` with `finish_reason=length`, or an unclosed JSON). Raising `max_tokens` alone does not fix this. Split the work: have the LLM emit only the compact core (e.g. the scene JavaScript, 40-60 lines) and assemble the outer shell deterministically with the `render_template` action (`template_file` asset + `{{placeholder}}` substitution from store values). Reasoning models also occasionally emit a trailing extra brace or stray text after valid JSON — the platform now trims up to 40 trailing characters and retries once on parse failure, but keep prompts explicit ("output only the JSON, no analysis text"). A real LLM call is always `kind=decision`, `executor=llm`, `effect=none`, with `output_contract=decision_envelope.v1` and explicit `decision_contract.consume`; persist files in a separate deterministic `writes_artifacts` node. Set `llm_options.max_tokens` high enough for reasoning models (their reasoning consumes most of the budget; too small a budget yields `PROVIDER_EMPTY_RESPONSE` with `finish_reason=length`) and `llm_options.timeout_seconds` above the slowest observed inference. Prefer `max_tokens: 20000` (8000 still failed intermittently in production). Make the prompt's output shape match the consume path exactly and include a precise JSON example. Follow the complete template in `references/authoring-checklist.md`. `validate_authored_cartridge.py` flags budgets below 20000 as `LLM_BUDGET_LOW` (warning).
11. Add models, permissions, failure policies, replay policies, and delivery fields only when the selected node effect requires them. Never invent a successful fallback for a missing external capability.
12. Run package preflight after each meaningful edit. Resolve blockers before adding more nodes.
13. Run the authored-cartridge validation after the final write. It validates final on-disk text, assets, Flow blockers, resource catalog, and model bindings; do not hand off a package until it reports `"ok": true`.
14. The root flow must declare the top-level wiring exactly like the template: `"start": "start"`, `protocol {id: CF-FARP, version: 1.0}`, `cartridge_id`, and a `start` state of `type: control` (NOT terminal). Missing `start` passes preflight but makes the runnable execute an empty run (structure check flags every node unreachable and finishes). `validate_authored_cartridge.py` now reports `FLOW_START_ENTRY_MISSING` (blocker) for this.
15. Give every `llm_prompt` node a node-level `retry_policy` (`{"max_attempts": 3, "initial_delay_seconds": 5, "max_delay_seconds": 30}`). Real reasoning models intermittently return `PROVIDER_EMPTY_RESPONSE` (finish_reason=length) — the engine auto-retries with the policy (verified in production: two real retries rescued a three.js scene run). `validate_authored_cartridge.py` warns `LLM_RETRY_POLICY_MISSING` when absent. For heavy code generation, `max_tokens: 20000` can still truncate — use 30000 with an explicit "output only the code, no analysis" prompt.

16. Apply a cartridge protocol certification label only through the certification API after its report passes. The skill's `cf-farp-1-0-authoring-verified` metadata proves this workflow was checked; it is not a cartridge certification label.
17. Run the relevant build and conformance commands before handing off.

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

## Runtime Verification

Verify the Flow actually runs before handoff. A clean graph is not evidence that nodes execute. The backend is `uvicorn` without `--reload`: after any `src/` change, restart it or a stale process can report `ACTION_EXECUTOR_MISSING` for a newly registered action even though the source contains it.

End-to-end run through the API:

```powershell
$run = Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8765/api/cartridge-runs -ContentType 'application/json' -Body (@{ cartridge_id = '<cartridge-id>'; inputs = @{ ... } } | ConvertTo-Json -Depth 6)
```

Then poll `GET /api/cartridge-runs/{run_id}` until `status` leaves `running`; while it is `paused_waiting_user`, approve the pending interaction:

```powershell
Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8765/api/cartridge-runs/$runId/pending-interaction/answer" -ContentType 'application/json' -Body '{"values":{"approval":"approved"}}'
```

A passing graph run ends `completed`, but that is not yet successful delivery. Require `delivery.status=delivered`, a primary identity equal to `manifest.delivery.primary_output`, and a passing data chain. For a Store-backed primary output, require a non-empty Delivery result. For an Artifact-backed primary output, require the matching `primary_artifact`, non-empty files under `.data/runtime/runs/<run_id>/artifacts/`, and readable Artifact URLs. Do not trust a green terminal node or an Artifact record without checking the underlying result. Use the final validator with `--run-id` and `--api-url`. The workbench opens the host-owned Run artifact folder through a scoped backend endpoint, so cartridges must emit Artifact references and must not embed local absolute paths. Keep domain-specific quality checks in the cartridge's own tests or DLC, not in this generic skill.

## Node Failure Protocol

Every node failure surfaces through the same envelope - no ad-hoc shapes, no raw exceptions leaking to the API:

- `run.error` / `run.errors[]` and the `lab_node_failed` event carry `runtime_error_envelope.v1`:
  `{ schema, error_id, code, category, message, node_id, source, retryable, recoverable, recovery_actions, cause_chain, http_status, missing_inputs }`.
- A declared `failure` edge (execution_plan `failure_route`) absorbs the failure and continues the flow.
  Without one, the run aborts (`status=failed`) with the envelope in `run.error`.

Stable error codes (declare failure edges for the ones your flow can survive):

- **Input/data**: `INPUT_REQUIRED` (missing required store key), `ARTIFACT_MISSING`, `ARTIFACT_READ_FAILED`, `DELIVERY_OUTPUT_MISSING`, `DECISION_CONSUME_FAILED`
- **Provider (retryable)**: `PROVIDER_TIMEOUT`, `PROVIDER_RATE_LIMITED`, `PROVIDER_UNAVAILABLE`, `PROVIDER_EMPTY_RESPONSE`, `PROVIDER_AUTH_FAILED`, `PROVIDER_MODEL_UNAVAILABLE`, `PROVIDER_CONFIGURATION_MISSING`
- **Tool/remote**: `TOOL_TIMEOUT`, `TOOL_EXECUTION_FAILED`, `TOOL_WORKER_CRASHED`, `DEPENDENCY_UNAVAILABLE`
- **Contract (fix the cartridge)**: `FLOW_CONTRACT_INVALID` (tool not declared / binding unsupported), `ACTION_EXECUTOR_MISSING` (action without executor), `NODE_EXECUTION_FAILED`

Design guidance:

- **Decision/LLM nodes**: output-format drift is normal. Declare a `failure` edge (retry the node or a fallback path) instead of assuming the LLM succeeds first try.
- **Tool/remote nodes**: timeouts and connectivity are retryable. A failure edge to a retry/degraded path is correct design; `retryable: true` in the envelope tells you so.
- **Every `type: process` node must declare at least one `failure` edge** (CF-FARP@1.0 `v10_failure_exit_missing` blocker) — this is a protocol requirement, not optional. But **failure exits can share one generic terminal** ("流程失败"): the precise failing node/code/message lives in `run.error` (`runtime_error_envelope.v1`), so per-step failure terminals are redundant. One shared failure terminal keeps the graph readable without losing detail. `validate_authored_cartridge.py` suggests sharing via `FAILURE_TERMINALS_MULTIPLE` (info) when several failure terminals exist.
- Every non-terminal node should have a non-failure outgoing edge or a failure edge; a node whose failure is not absorbed aborts the run. `validate_authored_cartridge.py` warns (`FLOW_SUCCESSOR_EDGE_MISSING`) when a node with a non-failure incoming edge has no non-failure outgoing edge.
- Never pattern-match on the raw `message` string; key off `code` / `recovery_actions`.

## Final Deliverable Validation

Run this after the final package save, after resource and model configuration are in place, and before reporting success:

```powershell
python docs/development/skills/cartridgeflow-flow-author/scripts/validate_authored_cartridge.py --repo . --package .data/user/dev_cartridges/<cartridge-id> --run-id <completed-run-id> --api-url http://127.0.0.1:8765
```

This is intentionally stricter than structural preflight. It rejects malformed UTF-8, replacement characters, `???` placeholder corruption, empty visible labels, Flow blockers, unavailable required resources, blocked model bindings, disguised LLM nodes, undeclared primary outputs, empty artifacts, incomplete Delivery snapshots, unreadable Artifact URLs, and broken data chains. A clean graph alone is not evidence that the user can read, run, or receive the cartridge output.

## Completion

Report the business nodes created, declared resources, both validation results, and any external configuration still required. Read `references/authoring-checklist.md` for field patterns and validation commands.

