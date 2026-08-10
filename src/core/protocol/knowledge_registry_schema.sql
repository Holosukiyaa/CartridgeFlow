PRAGMA application_id = 1128681554;
PRAGMA user_version = 1;
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

CREATE VIEW release_identity AS
SELECT
    protocol_id,
    version,
    COUNT(*) AS source_count,
    COUNT(DISTINCT bundle_digest) AS distinct_bundle_count,
    GROUP_CONCAT(source_id) AS sources
FROM protocol_release
GROUP BY protocol_id, version;
