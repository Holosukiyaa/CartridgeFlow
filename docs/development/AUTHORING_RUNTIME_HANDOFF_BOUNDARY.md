# Authoring To Runtime Handoff Boundary

Creator Studio owns intent, source references, prompts, AI proposals, selected
acceptance records, freeze lineage, and creator-local UI state. These are
private authoring facts and do not form runtime input.

Developer Console owns read-only development diagnostics over declared Flow
files, analysis, resources, tuning materialization, and preflight results. It
does not run cartridges, receive creator chat/session data, or own a runtime
installation.

The handoff endpoint accepts only the current, design-ready Creator revision
and its matching compile candidate. It materializes a signed CF-CRE archive
with a CF-FARP Root Flow, then returns signed-handoff metadata and a package
URL. It does not install, execute, or report a running cartridge.

The runtime receives only the downloaded signed CF-CRE archive, a runtime-owned
trust store, and runtime configuration. The reference toolkit verifies archive
integrity, publisher signature, trust binding, public-package boundaries, and
the declared CF-FARP Root Flow before any optional install or execution action.
It rejects archive paths and JSON fields for chat, creator/authoring sessions,
developer repositories, and frontend state. Source URLs, credentials, local
paths, Creator session records, and prompts are not handoff payload data.
