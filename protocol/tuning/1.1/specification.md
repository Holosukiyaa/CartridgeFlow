# CF-TUNING@1.1

CF-TUNING@1.1 stores creator-owned AI authoring facts. It is trusted only by CF-FARP@1.2 and never owns CF-FARP topology, executor, permission, code, or runtime delivery semantics.

`recipe_blueprint.v1` is an immutable portable recipe: creator intent, stable semantic steps, and digest-pinned source references. `recipe_instance.v1` is a fixed binding of a blueprint at a monotonically increasing revision. A source reference contains only stable `id`, `kind`, and SHA-256 `digest`; it contains no credential, endpoint value, local absolute path, or source payload.

An AI proposal is `authoring_change_set.v1`. Each change item has an immutable,
unique `id`, exact target identity, operation, and typed value. Supported
operations are `set_binding`, `set_step_intent`, and
`set_source_reference`; every target is validated against the pinned blueprint
before proposing and again before acceptance. Unsupported operations, unknown
targets, unsafe values, secrets, source payloads, endpoints, and local paths
fail closed.

Acceptance creates a separate immutable `authoring_acceptance.v1`; it never
rewrites proposal status. The acceptance pins the complete proposal, source
instance id/digest/revision, ordered selected item ids and values, and the
resulting immutable blueprint and instance. A caller may accept all items or a
non-empty, duplicate-free known subset. Selection is atomic: all selected
items apply deterministically or no result exists. Unselected items remain in
the immutable proposal and are not represented as accepted. A stale proposal,
invalid unselected item, or invalid selected item rejects the entire attempt.

Semantic changes create a new blueprint and a new instance with parent lineage;
old blueprints and instances are never modified. Freeze snapshots pin the exact
instance and blueprint digests plus semantic digests calculated from each step
and its binding. A frozen step cannot receive a binding or intent change unless
the caller follows an explicit new revision path; it is never silently
overwritten.

`authoring_freeze_snapshot.v1` explicitly lists every frozen step and its semantic digest, names the exact instance revision, and pins a deterministic compile reference. CF-FARP alone compiles that reference into executable topology and the CF-FARP contract. Implementations reject unknown capabilities, secrets, local paths, unsafe public values, executable content, and topology or execution fields.

CF-TUNING owns recipe facts and authoring revisions. CF-FARP owns Root Flow, topology, execution contracts, and signed-package runtime handoff. v1.0 facts and earlier v1.1 facts are not silently upgraded: migration creates new v1.1 blueprint, instance, proposal, acceptance, and explicit freeze facts, then records the prior digest as a redacted source reference.
