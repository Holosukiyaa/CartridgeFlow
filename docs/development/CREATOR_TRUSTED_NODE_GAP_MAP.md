# Creator Trusted Node Gap Map

This audit records the implementation gap between the historical fixed-template
path and the trusted-node dynamic recipe model in `PLAN.md`.

| Surface | Retained facts | Required correction |
|---|---|---|
| CF-TUNING 1.3 | Immutable revision and opaque mapping ideas | Keep historical; publish 1.4 with trusted node presets, dynamic recipes, capability gaps, and node-scoped fields. |
| CF-FARP 1.4 | Developer ownership of executable facts | Keep historical; publish 1.5 with trusted recipe materialization and Developer confirmation. |
| Base | Existing JSON stores, immutable authoring review, freeze lineage | Add generic preset registry, safe projection, recipe validator, adapters, and evidence. |
| Creator session | Project identity, review, freeze, sources, journey graph | Store exact preset revisions and mappings; forbid free node/topology mutation after composition. |
| Whole-flow AI | Strict JSON model adapter | Replace free semantic steps with bounded selection and connection of registered preset IDs. |
| Node AI | Preview and acceptance pipeline | Limit output to one selected node and its declared creator-safe fields. |
| Creator API/UI | Goal entry, draft view, node view | Compose atomically from registry; render preset fields; report capability gaps; remove free node controls. |
| Developer API/UI | Shared project projection | Show preset and mapping lineage; own materialization confirmation and signed handoff. |
| Runtime bridge | Deterministic CF-CRE build/sign/verify | Reject direct Creator handoff for trusted recipes and materialize CF-FARP 1.5 only from Developer. |
| Tests | Legacy contracts and handoff coverage | Add preset, composition, field isolation, capability gap, projection redaction, and Developer handoff coverage. |

No business preset belongs in Base. Tests may register fixtures; a real project
must receive its trusted nodes from Developer before Creator composition.
