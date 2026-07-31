# CF-FARP@1.0 - Authoring and static analysis

This file is a normative module of CF-FARP@1.0. The release is defined only by the same-version modules listed in README and CARTRIDGEFLOW-BASE@0.2.

## Authoring facts

CF-FARP@1.0 has two persisted authoring fact sets:

1. `states`: stable node identities, node contracts, input/output bindings, resources, permissions, effects and replay policies.
2. `execution_plan`: the only executable control topology, including its entry, stable edges and edge-specific contracts.

The following are not authoring facts: graph layout, visual styling, Analyzer relations, findings, derived summaries, normalized plan caches and runtime history. They may be cached, but never become a second source of execution semantics.

An authoring change MUST be a structured operation that changes one of these facts. Moving a line in the UI, deleting a derived relation or modifying a generated summary MUST NOT change the Flow.

## Structured inputs and outputs

Each process node MUST declare named `inputs` and `outputs`. Names are local port identities; display names and similarly named fields never create a binding.

```json
{
  "inputs": {
    "edition_name": {
      "required": true,
      "schema": {"type": "string", "minLength": 1},
      "binding": {"source": "store", "key": "daily_config", "path": "edition_name"}
    }
  },
  "outputs": {
    "editorial": {
      "target": {"type": "store", "key": "editorial_draft"},
      "schema_ref": "asset:schema.editorial_draft",
      "write_policy": "replace_revision"
    }
  }
}
```

Required inputs MUST have exactly one binding. An output MUST have a stable Store or Artifact identity and a schema. Two writers to the same identity require an explicit ordering or merge contract. The Analyzer MUST reject a required input that cannot be proven available on every reachable execution-plan path.

## Execution-plan authoring

Only `execution_plan.edges` control execution. An edge has a stable id, source, target and one of the kinds defined in [execution-plan.md](execution-plan.md): `sequence`, `fork`, `join`, `loop`, `batch`, `wait` or `failure`.

The authoring API MUST reject:

- a plan edge with an unknown state;
- ambiguous success edges or implicit joins;
- ordinary cycles instead of bounded loop contracts;
- waits without a stable resume identity and timeout failure;
- failure paths without a declared failure contract;
- any attempt to use display-only or derived relations as execution input.

The output of an interaction or human gate is ordinary structured data. A later node may consume that data, but a browser component, action label or UI relation MUST NOT select an execution target.

## Static analysis

The Analyzer is deterministic and has no business side effects. It consumes the current authoring facts and produces an Analysis Report containing:

- the normalized compiled plan and `plan_digest`;
- `source_digest` over the facts covered by the target;
- findings with stable code, severity, location and repair classification;
- derived data, resource and engineering relations marked as non-executable;
- the requested target and Analyzer identity.

`source_digest` MUST include the relevant states, execution plan, manifest contracts, declared assets, components and tool/resource contracts. It MUST NOT include presentation layout, local credentials, runtime history or the Analyzer's previous output. A stale report cannot pass development, package, publish or certification gates.

## Gates

Targets are ordered by strictness: `preview`, `development`, `package`, `publish`, `certification`. A stricter target may add blockers but never suppress a lower-target blocker. The Base MUST fail closed when the protocol, source digest, target or Analyzer identity does not match the report.

At minimum, analysis checks plan validity, path reachability, input availability, output identity conflicts, schema compatibility, resource bindings, permissions, side effects, replay policy, interaction contracts, tool transparency and primary delivery requirements.

## Authoring API

Authoring operations MUST be typed, revision-checked and auditable. They may create, update or remove a state; set an input/output contract; update a resource or tool binding; create, update or remove an execution-plan edge; analyze; or request a repair proposal.

An operation that changes authoring facts MUST increment the source revision. Concurrent writes MUST return a stable conflict rather than silently overwrite another author. Automatic repairs may only apply repairs classified as safe; confirmation and manual repairs require an explicit user decision and a fresh analysis report.
