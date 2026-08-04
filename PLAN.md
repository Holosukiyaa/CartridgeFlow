# CartridgeFlow Protocol-First Plan

## Product Decision

Creator Studio is an AI-assisted recipe composer built on Developer-owned,
versioned trusted node presets. A preset describes one reusable capability and
pins an immutable snapshot of a real executable Developer node. It is not a
fixed whole-flow template and it is not an abstract semantic placeholder.

The project chain is:

```text
Developer canvas process nodes
  -> published trusted presets plus executable mapping snapshots
  -> AI-composed Creator recipe
  -> reviewed and frozen CF-TUNING facts
  -> Developer-confirmed mappings and CF-FARP Root Flow
  -> signed CF-CRE handoff
```

The whole-flow AI may dynamically select, repeat, arrange, and connect trusted
node presets to answer a user's goal. The node-level AI may deepen one selected
node only through fields that its preset explicitly exposes. If no trusted
node can provide a required capability, the system reports a capability gap;
it never fabricates an abstract node that cannot be mapped to Developer.

Creator users see goals, sources, recipe nodes, editable choices, review state,
and readiness. They never see protocol fields, mapping keys, executors,
permissions, models, tools, secrets, or executable Root Flow facts. Developer
users own those implementation facts. Both roles use the original React Flow
workbench and the same dynamic chain graph. Creator semantics are the default;
Developer enables engineering semantics in canvas settings and publishes a
selected real node through the canvas's Trusted Nodes panel.

## Non-Negotiable Invariants

1. Every Creator-visible recipe node is an instance of a developer-authored
   trusted node preset with an immutable preset revision, mapping key, mapping
   digest, and executable Developer snapshot.
2. A whole-flow AI request may dynamically compose topology from compatible
   trusted presets. It must not emit a node type outside the supplied registry.
3. A node-level AI request may change only the creator-safe fields declared by
   that node's preset. It cannot change topology, mappings, or runtime facts.
4. A recipe records exact preset identities and revisions, node mappings,
   creator-safe values, source safety facts, relations, and review lineage.
5. Missing capabilities or mappings, invalid relations, unreviewed changes,
   stale revisions, unsafe sources, or unfrozen required nodes block handoff.
6. CF-TUNING owns trusted preset contracts and Creator design facts. CF-FARP
   owns executable Root Flow topology, execution plans, permissions, and the
   Developer-confirmed runtime handoff.
7. Base provides generic registry, validation, projection, and adapter behavior.
   It never ships business-specific trusted nodes or recipe templates.
8. A protocol release is supported only after validator, adapter, evidence, and
   tests exist. CF-CRE remains the only signed artifact handed to Runtime.

## Implemented Protocol Shape

Publish new versioned releases; never rewrite released contracts.

```text
CF-TUNING@1.4
  trusted_node_preset.v1
  trusted_node_registry.v1
  dynamic_creator_recipe.v1
  recipe_node_binding.v1
  creator_capability_gap.v1
  node-scoped change sets limited by preset field contracts
  review, preview, acceptance, freeze, readiness, and candidate lineage

CF-FARP@1.5
  exact trusted-subprotocol binding to the new CF-TUNING release
  trusted-recipe-to-Root-Flow mapping contract
  Developer confirmation before executable authority or signed handoff

CARTRIDGEFLOW-BASE
  generic trusted-node registry and revision validation
  creator-safe projection and constrained AI output validation
  deterministic Developer projection and mapping adapter
  release catalog and compatibility evidence
```

The earlier CF-TUNING 1.3 / CF-FARP 1.4 fixed-template contracts remain
historical releases. The corrected model is implemented by CF-TUNING@1.4 and
CF-FARP@1.5.

## Completed Delivery Sequence

### 1. Protocol and Base Audit

- Compare CF-TUNING 1.0 through 1.3 against the trusted-node model.
- Identify Creator store and bridge facts that can be retained.
- Identify generic semantic steps and other paths without stable mappings.
- Record the validators, adapters, APIs, projections, and tests that must change.

Acceptance: a written gap map covers every affected contract and surface.

### 2. Versioned Protocol Release

- Create the corrected CF-TUNING release with preset, registry, dynamic recipe,
  capability-gap, and node-scoped mutation contracts.
- Create the matching CF-FARP host release with exact trusted binding and
  Developer-owned materialization semantics.
- Update catalog, Base declarations, governance, and conformance evidence only
  when the behavior is implemented.

Acceptance: governance passes and unknown presets, mappings, fields, relations,
and stale revisions fail closed.

### 3. Base Implementation

- Implement generic Developer registration of trusted node presets.
- Implement Creator-safe registry projection with mapping details removed.
- Implement validated dynamic recipe composition from registered presets.
- Implement field-level node mutation and immutable review lineage.
- Implement deterministic projection to Developer and CF-FARP materialization.
- Require publication from a real Developer `process` node, store an immutable
  topology-free execution snapshot, and reject mapping-free registrations.

Acceptance: a fully mapped frozen recipe can reach Developer; an unmappable
node such as a generic "first-week output" is returned as a capability gap.

### 4. Authoring Skills

- Create a whole-flow product skill that receives a goal and creator-safe
  registry, composes a dynamic recipe, and reports missing capabilities.
- Create a node-expansion product skill that receives one preset contract and
  current values, then emits a previewable node-scoped CF-TUNING change set.
- Provide concise Codex skill packages for maintaining these product paths.

Acceptance: both skills define inputs, outputs, refusal conditions, protocol
checks, and realistic prompts; neither can invent mappings or runtime facts.

### 5. Creator Studio Projection

- Replace free-form node invention with trusted-registry composition.
- Default to one empty start node, then replace it with the composed draft.
- Keep overall draft review and single-node deepening as explicit modes.
- Render only creator-safe labels and preset-approved editable fields.
- Surface readiness and capability gaps in creator language.
- Use the original workbench as the single frontend surface; keep Creator as
  the default projection and reveal engineering semantics only through settings.

Acceptance: an AI daily report can combine several suitable trusted source and
processing nodes dynamically, and every visible node is traceable internally.

### 6. Developer and Runtime Handoff

- Show the same recipe and immutable preset/mapping lineage in Developer.
- Require Developer confirmation before CF-FARP materialization.
- Produce and verify the signed CF-CRE only after successful materialization.
- Materialize the pinned Developer `process` state and explicit CF-FARP failure
  exits instead of emitting non-executable `semantic_step` placeholders.

Acceptance: end-to-end tests prove trusted presets -> dynamic Creator recipe ->
Developer confirmation -> Root Flow -> signed CF-CRE, without Creator facts
acquiring executable authority.

## Explicitly Out of Scope Until This Plan Is Complete

- AI invention of unmapped node capabilities.
- Creator-side creation of tools, models, executors, permissions, or secrets.
- Direct Creator-to-Runtime handoff without Developer materialization.
- Runtime queue, artifact history, or production delivery UI in Creator Studio.
- Cosmetic UI work beyond readability needed to validate this behavior.
