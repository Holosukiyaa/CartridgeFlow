# CF-TUNING@1.1

CF-TUNING@1.1 stores creator-owned AI authoring facts. It is trusted only by CF-FARP@1.2 and never owns CF-FARP topology, executor, permission, code, or runtime delivery semantics.

`recipe_blueprint.v1` is an immutable portable recipe: creator intent, stable semantic steps, and digest-pinned source references. `recipe_instance.v1` is a fixed binding of a blueprint at a monotonically increasing revision. A source reference contains only stable `id`, `kind`, and SHA-256 `digest`; it contains no credential, endpoint value, local absolute path, or source payload.

An AI proposal is `authoring_change_set.v1`. It names the exact instance id and `expected_revision`, contains structured proposed edits, and remains immutable. Acceptance fails closed when the proposal is stale. An AI never silently freezes a step or changes a frozen semantic fact.

`authoring_freeze_snapshot.v1` explicitly lists every frozen step and its semantic digest, names the exact instance revision, and pins a deterministic compile reference. CF-FARP alone compiles that reference into executable topology and the CF-FARP contract. Implementations reject unknown capabilities, secrets, local paths, unsafe public values, executable content, and topology or execution fields.

CF-TUNING owns recipe facts and authoring revisions. CF-FARP owns Root Flow, topology, execution contracts, and signed-package runtime handoff. A v1.0 tuning repository is not silently upgraded: migration creates a new v1.1 blueprint, instance, reviewed change set, and explicit freeze snapshot, then records the source release digest as a redacted source reference.
