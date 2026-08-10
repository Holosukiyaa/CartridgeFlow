PRAGMA application_id = 1128681554;
PRAGMA user_version = 3;
PRAGMA foreign_keys = ON;

CREATE TABLE registry_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
) STRICT;

CREATE TABLE registry_source (
    source_id TEXT PRIMARY KEY,
    manifest_path TEXT NOT NULL,
    manifest_digest TEXT NOT NULL,
    source_digest TEXT NOT NULL
) STRICT;

CREATE TABLE registry_source_boundary (
    source_id TEXT PRIMARY KEY REFERENCES registry_source(source_id) ON DELETE CASCADE,
    role TEXT,
    authority TEXT,
    responsibility_boundary TEXT
) STRICT;

CREATE TABLE protocol_family (
    source_id TEXT NOT NULL REFERENCES registry_source(source_id) ON DELETE CASCADE,
    protocol_id TEXT NOT NULL,
    name TEXT,
    owner TEXT,
    responsibility_boundary TEXT,
    exclusions_json TEXT NOT NULL DEFAULT '[]',
    PRIMARY KEY (source_id, protocol_id)
) STRICT;

CREATE TABLE protocol_release (
    release_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES registry_source(source_id) ON DELETE CASCADE,
    protocol_id TEXT NOT NULL,
    version TEXT NOT NULL,
    name TEXT,
    category TEXT NOT NULL,
    lifecycle TEXT,
    specification_status TEXT,
    implementation_status TEXT,
    runtime_adapter TEXT,
    release_path TEXT NOT NULL,
    release_digest TEXT NOT NULL,
    bundle_digest TEXT NOT NULL,
    manifest_entry_json TEXT,
    release_json TEXT NOT NULL,
    UNIQUE (source_id, protocol_id, version),
    FOREIGN KEY (source_id, protocol_id)
        REFERENCES protocol_family(source_id, protocol_id)
) STRICT;

CREATE TABLE artifact (
    artifact_id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES registry_source(source_id) ON DELETE CASCADE,
    release_key TEXT REFERENCES protocol_release(release_key) ON DELETE CASCADE,
    artifact_path TEXT NOT NULL,
    artifact_kind TEXT NOT NULL,
    media_type TEXT NOT NULL,
    byte_size INTEGER NOT NULL,
    content_digest TEXT NOT NULL,
    content BLOB NOT NULL,
    text_content TEXT,
    UNIQUE (source_id, artifact_path)
) STRICT;

CREATE TABLE document_section (
    section_key TEXT PRIMARY KEY,
    artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id) ON DELETE CASCADE,
    release_key TEXT REFERENCES protocol_release(release_key) ON DELETE CASCADE,
    anchor TEXT NOT NULL,
    heading TEXT NOT NULL,
    heading_level INTEGER NOT NULL,
    line_start INTEGER NOT NULL,
    line_end INTEGER NOT NULL,
    content TEXT NOT NULL
) STRICT;

CREATE TABLE release_feature (
    release_key TEXT NOT NULL REFERENCES protocol_release(release_key) ON DELETE CASCADE,
    feature TEXT NOT NULL,
    PRIMARY KEY (release_key, feature)
) STRICT;

CREATE TABLE release_relation (
    relation_id INTEGER PRIMARY KEY,
    source_release_key TEXT NOT NULL REFERENCES protocol_release(release_key) ON DELETE CASCADE,
    relation_type TEXT NOT NULL,
    target_source_id TEXT,
    target_protocol_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (
        source_release_key,
        relation_type,
        target_protocol_id,
        target_version,
        metadata_json
    )
) STRICT;

CREATE TABLE source_policy (
    source_id TEXT NOT NULL REFERENCES registry_source(source_id) ON DELETE CASCADE,
    policy_key TEXT NOT NULL,
    target_protocol_id TEXT NOT NULL,
    target_version TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (source_id, policy_key)
) STRICT;

CREATE TABLE implementation_manifest (
    implementation_key TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES registry_source(source_id) ON DELETE CASCADE,
    implementation_id TEXT NOT NULL,
    implementation_name TEXT,
    implementation_version TEXT NOT NULL,
    environment TEXT,
    base_protocol_id TEXT,
    base_protocol_version TEXT,
    artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
    manifest_digest TEXT NOT NULL,
    UNIQUE (source_id, implementation_id, implementation_version)
) STRICT;

CREATE TABLE implementation_support (
    support_id INTEGER PRIMARY KEY,
    implementation_key TEXT NOT NULL REFERENCES implementation_manifest(implementation_key) ON DELETE CASCADE,
    support_kind TEXT NOT NULL,
    target_id TEXT NOT NULL,
    target_version TEXT NOT NULL DEFAULT '',
    support_status TEXT NOT NULL,
    runtime_adapter TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (implementation_key, support_kind, target_id, target_version)
) STRICT;

CREATE TABLE implementation_evidence (
    evidence_key TEXT PRIMARY KEY,
    implementation_key TEXT NOT NULL REFERENCES implementation_manifest(implementation_key) ON DELETE CASCADE,
    evidence_id TEXT NOT NULL,
    verification TEXT NOT NULL,
    implementation_json TEXT NOT NULL DEFAULT '[]',
    positive_tests_json TEXT NOT NULL DEFAULT '[]',
    failure_tests_json TEXT NOT NULL DEFAULT '[]',
    details_json TEXT NOT NULL DEFAULT '{}',
    artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
    UNIQUE (implementation_key, evidence_id)
) STRICT;

CREATE TABLE governance_finding (
    finding_id INTEGER PRIMARY KEY,
    severity TEXT NOT NULL,
    finding_type TEXT NOT NULL,
    source_id TEXT,
    release_key TEXT,
    protocol_id TEXT,
    version TEXT,
    message TEXT NOT NULL,
    details_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'open'
) STRICT;

CREATE TABLE data_contract_family (
    contract_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    layer INTEGER NOT NULL CHECK (layer BETWEEN 1 AND 4),
    domain TEXT NOT NULL,
    domain_order INTEGER NOT NULL DEFAULT 0,
    sort_order INTEGER NOT NULL DEFAULT 0,
    purpose TEXT NOT NULL,
    owner TEXT NOT NULL,
    visibility TEXT NOT NULL CHECK (visibility IN ('public', 'internal', 'mixed'))
) STRICT;

CREATE TABLE data_contract_release (
    contract_release_key TEXT PRIMARY KEY,
    contract_id TEXT NOT NULL REFERENCES data_contract_family(contract_id) ON DELETE CASCADE,
    version TEXT NOT NULL,
    lifecycle TEXT NOT NULL,
    generation TEXT NOT NULL CHECK (generation IN ('legacy', 'next')),
    definition_kind TEXT NOT NULL CHECK (
        definition_kind IN ('normative_section', 'normative_document', 'json_schema', 'machine_contract')
    ),
    source_id TEXT NOT NULL REFERENCES registry_source(source_id),
    owner_protocol_release_key TEXT NOT NULL REFERENCES protocol_release(release_key),
    definition_artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
    definition_section_key TEXT REFERENCES document_section(section_key),
    schema_artifact_id TEXT REFERENCES artifact(artifact_id),
    compatibility_policy TEXT NOT NULL,
    content_digest TEXT NOT NULL,
    notes TEXT NOT NULL DEFAULT '',
    UNIQUE (contract_id, version)
) STRICT;

CREATE TABLE data_contract_protocol_binding (
    contract_release_key TEXT NOT NULL REFERENCES data_contract_release(contract_release_key) ON DELETE CASCADE,
    protocol_release_key TEXT NOT NULL REFERENCES protocol_release(release_key) ON DELETE CASCADE,
    binding_role TEXT NOT NULL CHECK (binding_role IN ('defines', 'uses', 'carries', 'supports')),
    required INTEGER NOT NULL DEFAULT 1 CHECK (required IN (0, 1)),
    notes TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (contract_release_key, protocol_release_key, binding_role)
) STRICT;

CREATE TABLE data_contract_rule (
    rule_key TEXT PRIMARY KEY,
    contract_release_key TEXT NOT NULL REFERENCES data_contract_release(contract_release_key) ON DELETE CASCADE,
    rule_code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('blocker', 'error', 'warning', 'info')),
    rule_kind TEXT NOT NULL CHECK (rule_kind IN ('shape', 'semantic', 'boundary', 'compatibility', 'integrity')),
    description TEXT NOT NULL,
    validator_ref TEXT,
    UNIQUE (contract_release_key, rule_code)
) STRICT;

CREATE TABLE data_contract_usage (
    usage_key TEXT PRIMARY KEY,
    contract_release_key TEXT NOT NULL REFERENCES data_contract_release(contract_release_key) ON DELETE CASCADE,
    stage TEXT NOT NULL,
    actor TEXT NOT NULL,
    direction TEXT NOT NULL CHECK (direction IN ('producer', 'consumer')),
    notes TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE TABLE data_contract_example (
    example_key TEXT PRIMARY KEY,
    contract_release_key TEXT NOT NULL REFERENCES data_contract_release(contract_release_key) ON DELETE CASCADE,
    example_kind TEXT NOT NULL CHECK (example_kind IN ('valid', 'invalid')),
    artifact_id TEXT NOT NULL REFERENCES artifact(artifact_id),
    description TEXT NOT NULL,
    expected_error_code TEXT
) STRICT;

CREATE TABLE data_contract_migration (
    migration_key TEXT PRIMARY KEY,
    from_contract_release_key TEXT NOT NULL REFERENCES data_contract_release(contract_release_key) ON DELETE CASCADE,
    to_contract_release_key TEXT REFERENCES data_contract_release(contract_release_key),
    migration_kind TEXT NOT NULL,
    compatibility TEXT NOT NULL,
    transformer_ref TEXT,
    notes TEXT NOT NULL DEFAULT ''
) STRICT;

CREATE INDEX protocol_release_identity_idx
    ON protocol_release(protocol_id, version);
CREATE INDEX artifact_release_idx
    ON artifact(release_key, artifact_kind);
CREATE INDEX section_release_idx
    ON document_section(release_key, artifact_id);
CREATE INDEX relation_target_idx
    ON release_relation(target_protocol_id, target_version);
CREATE INDEX finding_identity_idx
    ON governance_finding(protocol_id, version, severity);
CREATE INDEX implementation_support_target_idx
    ON implementation_support(target_id, target_version, support_status);
CREATE INDEX implementation_evidence_verification_idx
    ON implementation_evidence(verification, evidence_id);
CREATE INDEX data_contract_family_tree_idx
    ON data_contract_family(layer, domain_order, domain, sort_order, contract_id);
CREATE INDEX data_contract_release_lifecycle_idx
    ON data_contract_release(contract_id, lifecycle, version);
CREATE INDEX data_contract_binding_protocol_idx
    ON data_contract_protocol_binding(protocol_release_key, binding_role);
CREATE INDEX data_contract_rule_release_idx
    ON data_contract_rule(contract_release_key, severity, rule_code);
CREATE INDEX data_contract_usage_release_idx
    ON data_contract_usage(contract_release_key, stage, direction);

CREATE VIEW release_identity AS
SELECT
    protocol_id,
    version,
    COUNT(*) AS source_count,
    COUNT(DISTINCT bundle_digest) AS distinct_bundle_count,
    GROUP_CONCAT(source_id) AS sources
FROM protocol_release
GROUP BY protocol_id, version;

CREATE VIEW source_overview AS
SELECT
    source.source_id,
    boundary.role,
    boundary.authority,
    boundary.responsibility_boundary,
    source.manifest_digest,
    source.source_digest,
    COUNT(DISTINCT release.release_key) AS release_count,
    COUNT(DISTINCT artifact.artifact_id) AS artifact_count
FROM registry_source AS source
LEFT JOIN registry_source_boundary AS boundary ON boundary.source_id = source.source_id
LEFT JOIN protocol_release AS release ON release.source_id = source.source_id
LEFT JOIN artifact AS artifact ON artifact.source_id = source.source_id
GROUP BY source.source_id, boundary.role, boundary.authority,
    boundary.responsibility_boundary, source.manifest_digest, source.source_digest;

CREATE VIEW protocol_release_overview AS
SELECT
    release.source_id,
    release.protocol_id,
    release.version,
    release.name,
    release.category,
    release.lifecycle,
    release.specification_status,
    release.implementation_status,
    release.runtime_adapter,
    release.release_path,
    release.bundle_digest,
    COUNT(artifact.artifact_id) AS artifact_count
FROM protocol_release AS release
LEFT JOIN artifact ON artifact.release_key = release.release_key
GROUP BY release.release_key;

CREATE VIEW protocol_document AS
SELECT
    artifact.source_id,
    release.protocol_id,
    release.version,
    artifact.artifact_path,
    artifact.artifact_kind,
    artifact.media_type,
    artifact.content_digest,
    artifact.text_content AS content
FROM artifact
LEFT JOIN protocol_release AS release ON release.release_key = artifact.release_key
WHERE artifact.text_content IS NOT NULL;

CREATE VIEW protocol_outline AS
SELECT
    artifact.source_id,
    release.protocol_id,
    release.version,
    artifact.artifact_path,
    section.anchor,
    section.heading,
    section.heading_level,
    section.line_start,
    section.line_end
FROM document_section AS section
JOIN artifact ON artifact.artifact_id = section.artifact_id
LEFT JOIN protocol_release AS release ON release.release_key = section.release_key;

CREATE VIEW data_contract_overview AS
SELECT
    family.contract_id,
    family.display_name,
    family.layer,
    family.domain,
    family.domain_order,
    family.sort_order,
    family.purpose,
    family.owner,
    family.visibility,
    contract.version,
    contract.lifecycle,
    contract.generation,
    contract.definition_kind,
    contract.source_id,
    owner.protocol_id AS owner_protocol_id,
    owner.version AS owner_protocol_version,
    artifact.artifact_path AS definition_path,
    section.heading AS definition_heading,
    contract.compatibility_policy,
    contract.content_digest,
    contract.notes,
    (SELECT COUNT(*) FROM data_contract_rule AS rule
        WHERE rule.contract_release_key = contract.contract_release_key) AS rule_count,
    (SELECT COUNT(*) FROM data_contract_usage AS usage
        WHERE usage.contract_release_key = contract.contract_release_key) AS usage_count,
    (SELECT COUNT(*) FROM data_contract_example AS example
        WHERE example.contract_release_key = contract.contract_release_key) AS example_count
FROM data_contract_release AS contract
JOIN data_contract_family AS family ON family.contract_id = contract.contract_id
JOIN protocol_release AS owner ON owner.release_key = contract.owner_protocol_release_key
JOIN artifact ON artifact.artifact_id = contract.definition_artifact_id
LEFT JOIN document_section AS section ON section.section_key = contract.definition_section_key;
