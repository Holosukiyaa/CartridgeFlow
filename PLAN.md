# CartridgeFlow Protocol-First Plan

## Product Decision

Creator Studio is not a free-form workflow generator and must not invent
business nodes that have no Developer mapping. It is the creator-facing
projection of a developer-owned, versioned recipe template.

The project chain is:

```text
Developer preset template
  -> constrained Creator template instance
  -> reviewed and frozen CF-TUNING facts
  -> Developer mapping and CF-FARP Root Flow
  -> signed CF-CRE handoff
```

Creator users see goals, sources, steps, choices, and review status. They never
see protocol fields, executors, permissions, models, tools, secrets, or Root
Flow topology. Developer users own those implementation facts.

## Non-Negotiable Invariants

1. Every Creator-visible step originates from a developer-authored template
   step with a stable Developer mapping key.
2. A whole-flow AI request may select and instantiate a compatible template;
   it must not invent an unbounded recipe or an unmappable abstract step.
3. A node-level AI request may change only fields declared editable by that
   template step. It produces a reviewed, immutable CF-TUNING change set.
4. A template instance records exact template identity, revision, declared
   node mappings, source safety facts, semantic facts, and review lineage.
5. Missing mappings, invalid relations, unreviewed changes, stale revisions,
   unsafe sources, or unfrozen required steps block compilation.
6. CF-TUNING owns creator design facts only. CF-FARP owns executable Root Flow
   topology, execution plans, executors, permissions, and runtime handoff.
7. Base support is real behavior, not a catalog claim. A release is supported
   only after validation, compiler/adapter behavior, and tests exist.
8. CF-CRE remains the only signed artifact handed to Runtime.

## Target Protocol Shape

Publish new versioned releases; never rewrite released contracts.

```text
CF-TUNING next release
  developer_recipe_template.v1
  creator_recipe_instance.v1
  template_step_mapping.v1
  authoring_change_set.v1 limited by template field contracts
  review, preview, acceptance, freeze, readiness, and compile candidate facts

CF-FARP next release
  exact trusted-subprotocol binding to the new CF-TUNING release
  template-instance-to-Root-Flow mapping contract
  no transfer of Creator facts into executable authority without Developer
  compilation and validation

CARTRIDGEFLOW-BASE
  template registry validation
  mapping compiler/adapter
  release catalog and compatibility evidence
```

The exact release numbers are chosen during the protocol audit. A semantic
change requires a new CF-TUNING release and an exact new CF-FARP host release.

## Delivery Sequence

### 1. Protocol and Base Audit

- Compare CF-TUNING 1.0, 1.1, and 1.2 against the preset-template model.
- Identify the current Creator store and bridge facts that can be retained.
- Identify all places where the bridge currently emits generic semantic steps
  without a developer mapping.
- Define the minimal Base adapter required before any support declaration.

Acceptance: a written gap map names every contract, adapter, validator, and
test that must change.

### 2. Versioned Protocol Release

- Create the new CF-TUNING release directory with specification, release,
  profiles, and capabilities.
- Create the matching CF-FARP host release with exact trusted subprotocol
  binding and mapping ownership.
- Update the release manifest, Base declarations, governance record, and
  protocol conformance evidence.

Acceptance: protocol governance audit passes; incompatible templates,
instances, mappings, and change sets fail closed.

### 3. Base Implementation

- Implement developer preset-template registration and validation.
- Implement constrained Creator instance creation and field-level mutation
  validation.
- Implement deterministic mapping from frozen template instances to Developer
  input and then CF-FARP Root Flow.
- Preserve immutable review, freeze, candidate, and handoff lineage.

Acceptance: a supported Base can compile only a fully mapped, frozen instance;
an unmappable node such as a generic "first-week output" fails before Developer
handoff.

### 4. Authoring Skills

- Create a whole-flow generation skill. It must discover and select a
  developer preset, instantiate it, and fill only declared Creator fields.
- Create a node-expansion skill. It must read the selected template step,
  deepen only permitted fields, and output a previewable CF-TUNING change set.
- Both skills must refuse requests that require a new preset and report the
  missing developer capability instead of fabricating a flow.

Acceptance: each skill has explicit inputs, outputs, refusal conditions,
protocol checks, and realistic example prompts.

### 5. Creator Studio Projection

- Replace free-form default recipe generation with preset selection and
  constrained instance generation.
- Keep the shared project chain graph, but display only creator-safe labels
  and template-approved fields.
- Make overall draft review and single-node expansion two explicit states.
- Surface readiness and blocked mappings in creator language; do not expose
  implementation details.

Acceptance: an AI daily report request shows only steps from a selected preset;
each visible node can be traced to a Developer mapping key.

### 6. Developer and Runtime Handoff

- Show the same frozen instance and mapping lineage in Developer Console.
- Compile through the new CF-FARP mapping contract.
- Produce and verify the signed CF-CRE handoff.

Acceptance: end-to-end test proves template -> Creator instance -> Developer
mapping -> Root Flow -> signed CF-CRE, with no creator-only fact acquiring
runtime authority.

## Explicitly Out of Scope Until This Plan Is Complete

- Free-form AI flow invention.
- Creator-side creation of executable nodes, tools, models, permissions, or
  Root Flow topology.
- Runtime execution, queue, artifact history, or production delivery UI in
  Creator Studio.
- Cosmetic UI work beyond readability needed to validate the above behavior.
