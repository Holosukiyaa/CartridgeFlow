# CF-TUNING@1.4

CF-TUNING@1.4 owns developer-authored trusted node presets and creator-safe,
dynamically composed recipe facts. It is trusted only by CF-FARP@1.5.

`trusted_node_preset.v1` declares immutable identity and revision, a creator
label and description, matching terms, creator-editable field contracts,
defaults, and one opaque Developer mapping key. The key is never part of a
Creator projection.

`trusted_node_registry.v1` pins the current revision and digest of each preset.
Base provides the generic registry but ships no business presets.

`dynamic_creator_recipe.v1` may contain any acyclic arrangement of one to eight
node instances. Every instance must pin a registered preset identity, revision,
digest, and mapping. A preset may be instantiated more than once. Relations
may only connect known instances and use `uses`, `produces`, or `informs`.

`creator_capability_gap.v1` is the only valid whole-flow result when the
registry cannot satisfy the goal. It describes creator-facing missing
capabilities without inventing mappings or executable facts.

After composition, node-level changes may replace creator values for exactly
one node and only fields declared by its pinned preset. They use immutable
review, preview, acceptance, reversal, freeze, readiness, and candidate
lineage. Node-level changes cannot alter topology, preset identity, mapping,
executors, permissions, models, tools, secrets, code, endpoints, local paths,
or Root Flow facts.

CF-TUNING compile candidates are design authority only. CF-FARP materialization
and Developer confirmation are required before executable authority exists.
