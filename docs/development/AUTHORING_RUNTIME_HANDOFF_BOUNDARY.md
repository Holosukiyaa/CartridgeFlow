# Authoring To Runtime Handoff Boundary

Creator owns intent, safe field values, AI proposals, reviewed acceptance
records, and review lineage. These are private authoring facts and never become
runtime authority directly.

Developer authority enters earlier, through immutable trusted-node publications
and their executable mapping snapshots. A Creator project does not open a
Developer workspace or require a second project-specific confirmation.

The sole Creator package endpoint accepts only the expected current revision.
It derives the compile candidate internally, validates every reviewed node and
mapping snapshot, materializes a CF-FARP@1.6 Root Flow, builds and verifies a
signed CF-CRE archive, then returns only filename, URL, status, and signature
verification. It does not expose the candidate, Root Flow, or mapping lineage.

The runtime receives only the downloaded signed CF-CRE archive, a runtime-owned
trust store, and runtime configuration. The reference toolkit verifies archive
integrity, publisher signature, trust binding, public-package boundaries, and
the declared CF-FARP Root Flow before any optional install or execution action.
It rejects archive paths and JSON fields for chat, creator/authoring sessions,
developer repositories, and frontend state. Source URLs, credentials, local
paths, Creator session records, and prompts are not handoff payload data.
