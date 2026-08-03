# Authoring To Runtime Handoff Boundary

Creator Studio owns intent, source references, AI proposals, selected acceptance
records, freeze lineage, and creator-local UI state. These are private authoring
facts and do not form runtime input.

Developer Console owns read-only development diagnostics over declared Flow
files, analysis, resources, tuning materialization, and preflight results. It
does not run cartridges, receive creator chat/session data, or own a runtime
installation.

The runtime receives only a signed CF-CRE archive plus a runtime-owned trust
store and runtime configuration. The reference toolkit verifies the archive's
integrity, publisher signature, trust binding, and public FARP payload before
installing or executing it. It rejects archive paths and JSON fields for chat,
creator/authoring sessions, developer repositories, and frontend state.

There is currently no accepted backend/core bridge from an authoring
`compile_candidate` to a materialized `root.flow.json` and then to the
production package endpoint. The candidate is deterministic provenance for an
accepted, frozen creator revision, but it is not a runtime cartridge handoff.
The backend/core owners must add that explicit materialization and packaging
bridge, with lineage from acceptance and freeze digests into the signed
CF-CRE payload, before claiming a single end-to-end authoring-to-runtime
generation path.
