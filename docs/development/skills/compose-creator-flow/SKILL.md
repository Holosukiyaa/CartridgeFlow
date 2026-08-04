---
name: compose-creator-flow
description: Implement, extend, or repair CartridgeFlow Creator Studio whole-flow composition based on CF-TUNING@1.4 trusted node presets. Use when work touches trusted preset selection, dynamic Creator recipe topology, capability-gap refusal, creator-safe registry projection, or the `/api/creator/compose-recipe` path.
---

# Compose Creator Flow

Maintain the product runtime that turns a Creator goal into a dynamic recipe
made exclusively from Developer-registered trusted node presets.

## Workflow

1. Read `PLAN.md`, `protocol/tuning/1.4/specification.md`, and
   `protocol/flow-authoring/1.6/README.md`.
2. Treat `src/core/protocol/trusted_node_recipes.py` as the fail-closed contract
   boundary and `src/core/llm/creator_flow_skill.py` as the model adapter.
3. Give the model only creator-safe preset projections. Never include mapping
   keys, executors, tools, models, permissions, secrets, or Root Flow facts.
4. Accept only registered preset IDs, declared creator values, known node
   instances, and `uses`, `produces`, or `informs` relations.
5. Resolve preset revision, digest, and Developer mapping on the server after
   parsing model output.
6. Return `creator_capability_gap.v1` when the registry cannot satisfy a goal.
   Never fabricate a semantic step such as "define first-week output."
7. Keep business presets out of Base. Register fixtures only inside tests.
8. Treat initial composition and whole-draft recomposition as the same strict
   contract; recomposition atomically replaces the current draft and clears old reviews.
9. Verify protocol conformance, projection redaction, unknown preset refusal,
   relation cycle refusal, API behavior, and Creator Studio tests.

## Inputs And Outputs

Input: one Creator goal plus the current creator-safe trusted preset registry.

Success output: one `dynamic_creator_recipe.v1` whose nodes all pin exact
server-resolved preset lineage.

Refusal output: one `creator_capability_gap.v1` listing missing capabilities in
Creator language.
