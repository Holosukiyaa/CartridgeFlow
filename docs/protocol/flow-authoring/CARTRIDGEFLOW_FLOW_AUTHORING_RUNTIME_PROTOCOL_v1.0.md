# CartridgeFlow Flow Authoring Runtime Protocol v1.0

Protocol identifier: `CF-FARP-1.0`

Protocol status: `draft`

Implementation status: `unsupported`

Base support: no current Base implementation claims support for `CF-FARP@1.0`.

Relationship: this is an incremental extension of `CF-FARP@0.9` which freezes
the independent ExecutionPlan authoring contract. It does not modify, reinterpret,
or certify `CF-FARP@0.9` flows. No implementation may silently upgrade a v0.9
flow or use this document to claim that a v1.0 plan is runnable.

## 1. Scope and Status

This document defines authoring facts for an `ExecutionPlan`: the explicit control
relations that a future token runner, analyzer, and canvas must consume identically.
It does not specify or provide a runner, persistence format for live tokens,
checkpoint recovery, a compatibility implementation, or certification evidence.

`CF-FARP@1.0` is recognized as a draft contract only. A Base MUST reject it as
unsupported until all of the following exist and are evidenced together:

- a token runner that realizes every relation in this document;
- compatibility validation that invokes the v1.0 contract before business code;
- conformance evidence for success, failure, cancellation, persistence, and resume;
- certification evidence for the claimed Base capability set.

The release catalog keeps v0.9 as the current default. The current catalog uses
its recognized-but-not-executable lifecycle bucket for this draft so existing
compatibility reports return the stable `recognized_unsupported_protocol` finding
and the v0.9 migration target. That catalog implementation detail does not make
v1.0 a historical protocol or a supported runtime.

This is an independent CartridgeFlow contract. It neither imports nor accepts n8n
workflow JSON, n8n node names, n8n item iteration, n8n expression behavior, or
n8n source-code semantics.

## 2. Authoring Object

A v1.0 Root Flow declares the protocol and contains the only executable topology:

```json
{
  "protocol": {"id": "CF-FARP", "version": "1.0"},
  "states": {
    "start": {"type": "control"},
    "work": {"type": "process", "effect": "read_only"},
    "complete": {"type": "terminal"}
  },
  "execution_plan": {
    "schema": "cartridgeflow.execution_plan.v1",
    "entry": "start",
    "edges": []
  }
}
```

`execution_plan.entry` MUST name a state. Every edge MUST have a unique `id`, a
supported `kind`, and existing `from` and `to` state ids. An ExecutionPlan edge is
an executable declaration, not a canvas decoration. It MUST NOT set
`executable: false`.

The only v1.0 edge kinds are:

```text
sequence | fork | join | loop | batch | wait | failure
```

All successful token transitions are modeled by `sequence`, `fork`, `join`,
`loop`, `batch`, or `wait`. `failure` is a separate failure-only transition. A
source has one successful transition unless every successful edge from that source
is a member of one `fork`.

The following legacy or visual-only topology is prohibited in a v1.0 flow:

- root-level `edges` or `control_edges`;
- node `next`;
- node `action_route` or `action_routes`;
- node `failure_route`;
- a visible edge marked `executable: false`.

They have no runtime meaning under this contract and MUST fail authoring validation.

## 3. Sequence

A `sequence` edge moves one completed success token from `from` to `to`:

```json
{"id": "prepare_to_render", "kind": "sequence", "from": "prepare", "to": "render"}
```

It has no hidden condition, display-only behavior, or name-derived routing. A
state cannot use multiple sequence-like successful edges to make an implicit branch.
Use `fork`, a declared routing state, or a future versioned relation instead.

## 4. Fork

A fork creates one independently tracked token for each declared branch. Every
edge in one fork shares `fork.id`, shares `from`, and has a distinct `fork.branch`.
At least two branches are required.

```json
[
  {"id": "split_metadata", "kind": "fork", "from": "split", "to": "metadata", "fork": {"id": "prepare_assets", "branch": "metadata"}},
  {"id": "split_media", "kind": "fork", "from": "split", "to": "media", "fork": {"id": "prepare_assets", "branch": "media"}}
]
```

The token identity produced by a fork includes the fork id and branch. A future
runner MUST preserve that identity through batch, loop, wait, failure, checkpoint,
and trace records. It MUST NOT infer branch identity from state names or edge order.

## 5. Join

A join is the only way to merge multiple successful incoming tokens. All edges in
one join share `join.id`, `to`, `join.mode`, and an exact finite `join.branches`
set. Every incoming edge has one distinct `join.branch`; the set of those values
MUST equal `join.branches`. A join has at least two branches and one output state.

```json
{
  "id": "join_metadata",
  "kind": "join",
  "from": "metadata",
  "to": "publish",
  "join": {
    "id": "assets_ready",
    "mode": "all",
    "branch": "metadata",
    "branches": ["metadata", "media"]
  }
}
```

### 5.1 `all`

`all` holds each branch token until exactly one live token from every declared
branch is available for the same fork/loop/batch lineage. It emits one aggregate
token. Duplicate delivery for a branch, a missing required branch, cancellation,
or a branch failure is a runtime failure; it is never an implicit successful join.

### 5.2 `any`

`any` emits the first eligible branch token once. It MUST declare
`join.remaining` as either `cancel` or `drain` on every edge in the group. `cancel`
requests cancellation of remaining sibling tokens; `drain` records them as
non-emitting observations. Neither policy permits a second downstream emission.

### 5.3 `keyed`

`keyed` performs `all` independently for each value of the common `join.key_ref`.
All edges in the group MUST use the same non-empty value reference and the same
finite branch set. A future runner MUST persist the key value and lineage with each
pending partial group. It MUST reject an absent key, duplicate branch for one key,
or a key group that cannot satisfy its declared branches.

An ordinary target with more than one successful incoming edge is an implicit join
and MUST be rejected. The declared source of a `loop` is an exception: its initial
entry and its bounded iteration return are the two executable alternatives of that
one loop relation, not a join. A canvas may render any other implicit merge, but it
has no executable meaning.

## 6. Loop

A loop is the only relation allowed to close a control cycle. Its `loop` object
requires a stable `id`, positive integer `max_iterations`, a non-empty
`continue_when` value reference, and an `exit_to` state id.

```json
{
  "id": "retry_gate_to_body",
  "kind": "loop",
  "from": "retry_gate",
  "to": "retry_body",
  "loop": {
    "id": "bounded_retry",
    "max_iterations": 3,
    "continue_when": "$retry_gate.should_retry",
    "exit_to": "complete"
  }
}
```

When `continue_when` is true, the token traverses `to` and increments the loop
counter. Otherwise it traverses `exit_to`. `exit_to` is an executable alternative
of the same declared loop relation and MUST be renderable by the canvas. A runner
MUST fail before another body entry when `max_iterations` is reached. It MUST NOT
interpret a cycle built from sequence edges as a loop.

## 7. Batch

A batch edge converts an explicit finite input collection into bounded work tokens.
It requires `batch.id`, `items_ref`, positive integer `size`, positive integer
`max_concurrency` no greater than `size`, and `ordering` of `preserve` or
`unordered`.

```json
{
  "id": "files_to_render_batches",
  "kind": "batch",
  "from": "files_ready",
  "to": "render_file",
  "batch": {
    "id": "render_files",
    "items_ref": "$files_ready.files",
    "size": 10,
    "max_concurrency": 3,
    "ordering": "preserve"
  }
}
```

`preserve` means source collection order is retained in token identity and output
aggregation. `unordered` permits completion order to differ but does not permit
unbounded concurrency. The runtime MUST record the source item reference, batch
id, batch index, concurrency limit, and lineage for every emitted work token.

## 8. Wait

A wait edge persists a token until one declared resumption condition is satisfied.
It requires `wait.id`, `wait.mode`, positive `timeout_ms`, and a valid identifier
`resume_key`. Modes are `duration`, `signal`, and `condition`.

```json
{
  "id": "approval_wait",
  "kind": "wait",
  "from": "request_approval",
  "to": "approved",
  "wait": {
    "id": "approval_received",
    "mode": "signal",
    "signal": "approval.completed",
    "timeout_ms": 86400000,
    "resume_key": "approval_response"
  }
}
```

`duration` additionally requires positive `duration_ms`; `signal` requires
`signal`; and `condition` requires `condition_ref`. A wait timeout is a failure,
not a normal route. It therefore requires an explicit failure edge from the wait
source with `timeout` in `failure.causes`.

## 9. Failure

A failure edge is an explicit, executable alternative activated only by a matching
failure cause. It requires a stable `failure.id` and non-empty unique `causes` from
the following vocabulary:

```text
cancelled | exception | resource | retry_exhausted | timeout | validation
```

```json
{
  "id": "render_timeout",
  "kind": "failure",
  "from": "render_file",
  "to": "render_timeout_handler",
  "failure": {"id": "render_failed", "causes": ["timeout", "exception"]}
}
```

An executable action state (`type=process`, `type=action`, a side-effecting
`effect`, or `execution.may_fail=true`) MUST have at least one failure edge. The
same source cannot declare more than one failure edge for the same cause. A
`failure_policy` field, a legacy `failure_route`, an exception handler hidden in
code, or a canvas line does not satisfy this rule.

## 10. Static Rejection Rules

The normative authoring validator reports stable blocker codes:

| Situation | Code |
| --- | --- |
| Missing v1.0 declaration | `v10_root_flow_protocol_missing` |
| Missing or invalid plan | `v10_execution_plan_missing`, `v10_execution_plan_schema_invalid` |
| Unknown or malformed edge | `v10_execution_edge_kind_invalid`, `v10_execution_edge_endpoint_unknown` |
| Hidden legacy sequence/action/failure topology | `v10_implicit_sequence_forbidden`, `v10_legacy_action_route_forbidden`, `v10_legacy_failure_route_forbidden` |
| Visible but non-executable edge | `v10_visible_non_executable_edge` |
| Implicit merge | `v10_implicit_join_forbidden` |
| Invalid fork or join group | `v10_fork_group_invalid`, `v10_join_group_invalid` |
| Unbounded or implicit cycle | `v10_loop_contract_invalid`, `v10_implicit_cycle_forbidden` |
| Invalid batch or wait | `v10_batch_contract_invalid`, `v10_wait_contract_invalid` |
| Missing failure exit | `v10_failure_exit_missing` |
| Wait without timeout failure exit | `v10_wait_timeout_failure_missing` |

Findings identify `node_id` or `edge_id` where applicable. Validators MUST reject
these conditions deterministically and MUST NOT repair them by guessing a route.

## 11. Conformance and Future Promotion

The draft authoring conformance suite contains one valid and one invalid case for
each relation: sequence, fork, all join, any join, keyed join, loop, batch, wait,
and failure. It also covers implicit joins, unbounded loops, missing failure exits,
legacy action routes, and non-executable visible edges.

Passing this static suite means only that author facts obey this draft. It does not
make a v1.0 cartridge compatible, runnable, portable, or certifiable. Promotion
requires the full status conditions in section 1 and a new release decision; until
then `config/base/BASE_IMPLEMENTATION.json` MUST NOT list `CF-FARP@1.0`.
