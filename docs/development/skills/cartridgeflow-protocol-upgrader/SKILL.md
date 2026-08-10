---
name: cartridgeflow-protocol-upgrader
description: Upgrade CartridgeFlow protocol versions safely. Use when asked to change CF-FARP/Base Contract semantics, add a new protocol version, modify node type rules, dynamic input rules, decision/RAG/tool-plan behavior, compatibility or certification requirements, machine-readable protocol registry files, or base support declarations.
---

# CartridgeFlow Protocol Upgrader

Use this skill to make versioned protocol changes without silently breaking existing certified cartridges.

## Required First Reads

Before editing, read:

- The product lock at `config/protocol/protocol-registry.lock.json`.
- `current:protocol/governance/GOVERNANCE.md` from the pinned source database.
- The current release artifacts queried from `protocol_release_overview`.
- `current:protocol/catalog/release_manifest.json` from the source database.
- `config/base/BASE_IMPLEMENTATION.json`
- `references/upgrade-checklist.md` when applying an upgrade, not merely discussing one.

## Decision Rule

Treat a requested protocol change as a new version when it changes any of these:

- Node type semantics.
- Runtime execution semantics.
- Certification requirements.
- Compatibility report behavior.
- Manifest or root flow contract meaning.
- Tool, MCP, RAG, decision, input, or transfer boundaries.

Use an in-place documentation patch only for spelling, clarification that does not alter meaning, broken links, or examples that do not change rules.

## Upgrade Workflow

1. Preserve existing protocol meaning. Do not rewrite v0.1 to mean v0.2.
2. Export the relevant `current` artifacts to an ignored temporary workspace with `protocol-source/scripts/protocol_db.py export`; never recreate a committed protocol tree.
3. Author a complete version bundle in that temporary workspace, including its machine-readable `release.json`.
4. Add version-local `capabilities.json` and `profiles.json` when the protocol declares them, then publish the complete bundle into `protocol-source.sqlite` in one transaction.
5. Declare `runtime_adapter` and `features` in both release records. Reuse an existing adapter only when runtime semantics are unchanged; otherwise add a new adapter implementation and then declare it in `config/base/BASE_IMPLEMENTATION.json.supported_protocol_adapters` after tests support it.
6. Transactionally update the `current:protocol/governance/GOVERNANCE.md` artifact so future agents see the new protocol.
7. Add or update tests proving the registry, docs, and base support declarations are consistent.
8. Only apply certification labels after the relevant certification report passes.
9. Commit and push the embedded `protocol-source` submodule, then run `python scripts/update_protocol_registry.py` in CartridgeFlow to refresh the read-only SQLite copy and pinned submodule commit.

## Hard Boundaries

- Never loosen certification so one cartridge passes.
- Never treat a development-base behavior as portable unless protocol, base declaration, and capability declaration all agree.
- In CF-FARP v0.2 and later, user-facing business nodes may be unified as "process node + suffix", but protocol behavior must still be constrained by `type=process`, `kind`, `executor`, and `effect`.
- It is acceptable to merge transfer, retrieval, decision, gate, UI, and MCP execution under the same protocol `type=process`, but preserve hard behavior boundaries with `kind` and `effect`.
- In CF-FARP v0.3 and later, AI decision nodes that use `executor=llm` must be treated as structured decision producers. They must emit `decision_envelope.v1`, and `needs_user_input` must pause the run instead of letting downstream side-effect nodes execute.
- Do not claim `runtime_resume_after_user_input` unless the runtime can continue without replaying unsafe side effects. `paused_waiting_user_status` is a weaker capability than true resume.
- Never claim support for a protocol version in `config/base/BASE_IMPLEMENTATION.json` before runtime behavior, compatibility checks, and conformance tests exist.

## Output Standard

For any completed upgrade, report:

- New protocol artifact identity.
- New machine-readable release artifact identity.
- Changed capabilities/profiles.
- Whether the current base supports the new protocol.
- Tests run and result.
