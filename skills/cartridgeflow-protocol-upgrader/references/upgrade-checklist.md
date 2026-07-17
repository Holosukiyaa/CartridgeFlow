# CartridgeFlow Protocol Upgrade Checklist

Use this checklist when applying, not merely discussing, a protocol upgrade.

## 1. Classify The Change

Create a new protocol version if the change affects:

- Node type rules.
- Input timing or runtime interaction.
- Process / decision / retrieval semantics.
- Tool or MCP binding behavior.
- Tool-plan or schema validation behavior.
- Certification label requirements.
- Compatibility report behavior.
- Base support expectations.

Patch the current protocol only if meaning is unchanged.

## 2. Freeze Existing Versions

Existing protocol docs are historical contracts. Do not edit old versions to absorb new semantics.

Acceptable old-version edits:

- Typo fixes.
- Broken links.
- Clarifying notes that explicitly say they do not change the rule.
- Cross-reference to a newer version.

Unacceptable old-version edits:

- Changing what a node type means.
- Adding a requirement that certified cartridges did not need before.
- Changing certification conditions.
- Changing compatibility expectations.

## 3. Add Source Protocol Document

For `CF-FARP 0.x`, add:

```text
docs/protocol/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v0.x.md
```

The document should include:

- Protocol id and version.
- Status.
- Relationship to earlier versions. Use `supersedes` for a full replacement version and `extends` only for an explicitly incremental extension.
- New goals.
- Normative rules.
- Certification requirements.
- Migration guidance.
- Examples.

## 4. Add Machine-Readable Registry

Add:

```text
protocol/CF-FARP-0.x.json
```

The file should include:

- `schema_version`
- `id`
- `version`
- `name`
- `status`
- `supersedes` for a full replacement version, or `extends` for an explicitly incremental version
- registry file references
- source document path

## 5. Update Vocabulary

Update only vocabulary files that are required:

```text
protocol/profiles.json
protocol/capabilities.json
protocol/tool_packs.json
```

Adding vocabulary does not mean the current base supports it.

## 6. Do Not Overclaim Base Support

Do not add the new protocol to:

```text
BASE_IMPLEMENTATION.json.supported_protocols
```

until implementation exists for:

- Runtime execution behavior.
- Compatibility report checks.
- Certification checks.
- Conformance tests.
- UI or API behavior when relevant.

If partial support is intentionally declared, set status to `partial` and list conformance cases honestly.

For interactive decision upgrades, separate these capabilities:

- `decision_envelope_v1`: the runtime can represent the structured decision output.
- `decision_envelope_validate`: the runtime can reject invalid envelopes.
- `paused_waiting_user_status`: the runtime can stop after `needs_user_input`.
- `pending_interaction_record`: the runtime records the question and target store key.
- `runtime_resume_after_user_input`: the runtime can continue without replaying unsafe side effects.

Do not collapse these into one generic AI capability.

For CF-FARP v0.4 and later, separate explicit decision consumption from envelope validation:

- `decision_consume_contract`: the compatibility layer can validate `decision_contract.consume`.
- `decision_consume_projection`: the runtime can project `consume.path` into the explicit `consume.as` store key.

Do not add implicit output-name-derived consume keys to older protocols.

## 7. Update Agent Entry Points

Update:

```text
docs/protocol/agent.md
AGENT.md
```

Future agents must learn:

- Which protocol files are authoritative.
- Which version is stable vs draft.
- Whether a protocol version uses unified user-facing nodes with protocol-layer `kind` / `executor` / `effect`.
- Which skill to use for future upgrades.

## 8. Add Tests

Add or update tests for:

- Protocol registry discovers the new protocol.
- Base does not accidentally claim support.
- New vocabulary is valid.
- Old certified cartridges remain certified under their original version.

Prefer small conformance tests over broad integration tests for protocol registry changes.

## 9. Validate

Run at minimum:

```text
python -m json.tool protocol/CF-FARP-0.x.json
python -m json.tool protocol/profiles.json
python -m json.tool protocol/capabilities.json
python -m unittest discover -s tests\conformance
```

If implementation changed, also run targeted runtime/API/frontend tests.

## 10. Report

Final response should state:

- The new version.
- Files created or changed.
- Whether current base supports it.
- Certification impact.
- Tests run.
