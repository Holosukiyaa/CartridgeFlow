---
name: refine-creator-node
description: Implement, extend, or repair CartridgeFlow Creator Studio node-deepening behavior under CF-TUNING@1.4. Use when work touches one-node AI refinement, preset editable-field contracts, node-scoped authoring change sets, preview and acceptance, freeze state, or the trusted node refinement API and UI.
---

# Refine Creator Node

Maintain the product runtime that deepens one mapped Creator recipe node
without changing its identity, topology, mapping, or executable authority.

## Workflow

1. Read `PLAN.md` and `protocol/tuning/1.4/specification.md`.
2. Load the selected recipe node and its exact pinned preset revision.
3. Give the model only the node label, current creator values, and creator-safe
   editable field contracts through `src/core/llm/creator_node_skill.py`.
4. Accept only `{ "values": {...} }`. Validate every key and value type with
   `src/core/protocol/trusted_node_recipes.py`.
5. Convert the result into one `set_creator_binding` change targeting exactly
   the selected node. Preserve current fields omitted by the model.
6. Route the change through immutable proposal, preview, acceptance, reversal,
   and freeze lineage in `src/core/studio/authoring_service.py`.
7. Reject topology, preset, mapping, source, implementation, tool, model,
   permission, secret, endpoint, or multi-node changes.
8. Verify selected-node isolation, undeclared field refusal, creator-safe
   projection, stale revision refusal, and Creator Studio review behavior.

## Inputs And Outputs

Input: one selected node, its pinned creator-safe field contract and values,
one user refinement request, and the expected Creator revision.

Output: one previewable node-scoped CF-TUNING change set. No direct mutation is
allowed before Creator acceptance.
