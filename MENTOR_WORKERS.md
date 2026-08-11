# Mentor Worker Register

Project: CartridgeFlow clean-room protocol rebuild
Repository root: `C:\_HOLOLAB\code\CF WS\CartridgeFlow`
Protocol repository: `C:\_HOLOLAB\code\CF WS\CartridgeFlow\protocol-source`
DR repository: `C:\_HOLOLAB\code\CF WS\CartridgeFlow\DR`
Last updated: 2026-08-11 11:44 Asia/Shanghai
Mentor: Codex mentor-orchestrator

## Delivery Plan

This delivery rebuilds the protocol system from the current target business,
not by migrating or publishing the previous protocol identities. The future
AI-facing protocol database, browser and engineering guidance must contain only
the new four-layer system. The existing mixed protocol database is frozen until
the new source and product snapshot are accepted.

Workers must be launched in the dependency order recorded below. Worker 001
owns the authoritative protocol source model and database. Worker 010 is the
only owner of the product read-only registry snapshot and lock. Workers 002-007
implement isolated product boundaries after their declared prerequisites are
accepted. Worker 009 owns all new conformance and integration tests. The mentor
owns acceptance, non-fast-forward integration, preservation of the user's dirty
changes, and final cleanup.

The main worktree currently contains user changes that are not part of this
delivery. No worker may assume those changes are present, overwrite them, or
stage them. The DR directory is an independent Git repository and must be
worked in through its own worktree.

## Workers

| Worker | Status | Objective | Allowed write paths | Exclusions | Dependencies | Branch | Worktree | Acceptance evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| worker-001-protocol-source-rebuild | accepted | Build the clean four-layer authoritative protocol source and SQLite model. | `protocol-source/**` in the protocol repository | Main product code, DR, viewer, user planning files | None | `workers/worker-001-protocol-source-rebuild` | Removed after verified merge; branch retained | Accepted at `88a8440`; integrated into protocol `main` by merge `fc08310`. Exact 22-module/75-contract catalogs and deliberate-corruption tests pass. |
| worker-002-authoring-core-implement | planned | Implement CF-AUTHORING behavior in core authoring, Flow, capability and composition code. | `src/core/protocol/authoring_contract.py`, `capability_cartridges.py`, `capability_registry.py`, `creator_templates.py`, `flow_contract.py`, `tool_plan.py`, `trusted_node_recipes.py`, `tuning.py`; `src/core/lab/**`; selected authoring files under `src/core/studio/` | Protocol source/database, shared data-contract engine, Base manifest, distribution, runtime, backend, frontends, tests | 001 accepted and protocol source commit available | `workers/worker-002-authoring-core-implement` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-002-authoring-core-implement` | Authoring contract behavior and composition invariants run against the new catalog; no old protocol identity is executed. |
| worker-003-distribution-core-implement | planned | Implement new package, integrity, trust, installation and delivery-boundary behavior. | `src/core/cartridge/**` except files explicitly owned by worker 004; `src/core/protocol/release_builder.py`, `release_envelope.py`, `release_signing.py`, `certification.py`, `artifact_store.py`; `src/core/studio/release.py`, `portability.py`, `hygiene.py` | Protocol source/database, authoring core, runtime state machine, backend, frontends, tests | 001 and 002 accepted | `workers/worker-003-distribution-core-implement` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-003-distribution-core-implement` | New packages pass content, signature, trust, dependency and installation gates with positive and failure paths. |
| worker-004-runtime-core-implement | planned | Implement new host, execution, recovery and delivery semantics in Python runtime and runner. | `src/core/runtime/**`; `src/core/cartridge/runner.py`; `src/core/protocol/base_manifest.py`, `compatibility.py`, `data_contracts.py`, `report.py`, `release_catalog.py` | Protocol source/database, distribution files, DR, backend, frontends, tests | 001 accepted; 003 package boundary available | `workers/worker-004-runtime-core-implement` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-004-runtime-core-implement` | Host negotiation, state transitions, errors, checkpoint/recovery and delivery results use only the new runtime contracts. |
| worker-005-dr-runtime-implement | planned | Align the independent Go Desktop Runner with the new host and runtime contracts. | `shell/go/internal/runtimeprofile/**`, `shell/go/internal/verify/**`, `shell/go/internal/runner/**`, `shell/go/internal/scheduler/**`, `shell/go/internal/store/**`, related Go tests in those packages | Main repository files, protocol source, Python runtime, UI, unrelated Go packages | 001 and 004 accepted | `workers/worker-005-dr-runtime-implement` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-DR-worker-005-dr-runtime-implement` | `gofmt`, `go vet ./...`, and `go test ./... -count=1` pass; Python/Go host results agree. |
| worker-006-backend-boundary-align | planned | Align FastAPI request/response and publication/runtime routes to new contracts. | `src/backend/api_models.py`, `src/backend/main.py` | Core protocol implementation, protocol source/database, DR, frontend, tests | 001-004 accepted | `workers/worker-006-backend-boundary-align` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-006-backend-boundary-align` | API surface exposes only new contract identities, validates failure cases, and preserves same-origin product boundaries. |
| worker-007-product-surfaces-align | planned | Align Intent Studio and Capability Workshop payloads and visible states with the new protocol model. | `src/intent-studio/**`, `src/capability-workshop/**` | Backend, core protocol, protocol source/database, DR, tests outside browser fixtures | 001, 002 and 006 accepted | `workers/worker-007-product-surfaces-align` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-007-product-surfaces-align` | Both frontend builds/tests pass; semantic intent and technical capability surfaces do not expose old protocol concepts. |
| worker-008-viewer-context-clean | planned | Make the protocol browser and AI-facing project guidance expose only the new system. | `config/protocol-viewer/**`, `view-protocols.bat`, `AGENT.md`, `README.md`, `docs/development/FILE_INVENTORY.md` when present | SQLite contents and lock, product implementation, user UI changes, DR | 001 and 010 accepted | `workers/worker-008-viewer-context-clean` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-008-viewer-context-clean` | Browser tree shows four layers/modules/contracts only; static scan finds no old protocol identity in active guidance. |
| worker-009-conformance-gates-build | planned | Own the new rule, contract, state, error, cross-language and end-to-end verification suite. | `scripts/tests/**`, `scripts/validate_*.py`, `scripts/audit_*.py`, `scripts/run_conformance.py` | Product implementation, protocol source/database, viewer, user files, DR implementation | 001-007 accepted and 010 snapshot available | `workers/worker-009-conformance-gates-build` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-009-conformance-gates-build` | Deliberate protocol/code corruption fails closed; full Python and end-to-end gates pass. |
| worker-010-registry-snapshot-publish | planned | Publish the clean protocol source into the product read-only SQLite and lock it. | `config/protocol/**`, `scripts/update_protocol_registry.py` | Authoritative protocol source contents, product code, viewer, tests | 001 accepted | `workers/worker-010-registry-snapshot-publish` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-010-registry-snapshot-publish` | Product snapshot has one new source, matching database digest and source commit; updater rejects dirty/unpublished source. |

## Worker Reports

### worker-001-protocol-source-rebuild

- Prompt issued: 2026-08-11; delivery received and independently reviewed.
- Changed files: `AGENT.md`, `README.md`, `protocol-source.sqlite`, `registry/schema.sql`, `requirements.txt`, `scripts/protocol_db.py`, `scripts/publish_protocol_generation.py`; deleted `registry/migrate_v2_to_v3.sql` and `scripts/contract_catalog_v3.py`.
- Commit: `f9305813f425e3705415dc957c07ebac775c9a06` on `workers/worker-001-protocol-source-rebuild`; parent is the declared baseline `f20decf`; worktree clean; no push observed.
- Tests: Worker-reported source verification, deterministic publication, SQL coverage, JSON Schema examples, atomicity, forbidden-identity scan and `git diff --check` passed. Mentor reran `python scripts/protocol_db.py verify`, `python scripts/publish_protocol_generation.py verify` and `git diff --check`; all passed.
- Risks or follow-up: The source contains only 16 modules and 16 normative rules, one rule per module, while the accepted target architecture defines 22 modules. Missing first-class areas include Foundation `base` and `publication`; Authoring `data`, `presentation` and `integration`; Distribution `exposure`; Runtime `interaction` and `artifact`. The delivered `identity`, `vocabulary`, `evolution`, `install`, `negotiation` and combined `delivery` taxonomy also does not match the accepted module ownership. Contract coverage is therefore coverage of the worker's reduced catalog, not coverage of the business inventory. The mentor also proved a fail-open completeness gap on a temporary database: deleting the Authoring `capability` module and `cartridgeflow.authoring.capability` contract, refreshing digests, and running `verify_connection()` still returned zero errors with 15 contracts remaining. The verifier must own an explicit required module/contract manifest and deliberate-corruption tests, independent of the publication catalog. Resume this existing worker and commit the correction; do not create a replacement worktree.
- First mentor decision: Rejected on 2026-08-11. Do not merge, publish, or start dependent workers from `f9305813`.
- Follow-up changed files: `protocol-source.sqlite`, `scripts/protocol_db.py`, `scripts/publish_protocol_generation.py`.
- Follow-up commit: `67708e5ed8a9d6e2e1f34ddfe6a21600d269ff64`; parent is the first rejected commit `f9305813f425e3705415dc957c07ebac775c9a06`; branch and worktree are clean.
- Follow-up tests: Worker-reported verifier, publication verification, fresh rebuild, compileall, SQL checks and `git diff --check` passed. Mentor reran both verification commands and `git diff --check`; all passed.
- Follow-up finding: The database and publication source still contain the same 16 modules, 16 rules and 16 contracts. The required 22-module architecture was not implemented. The follow-up mainly added field, artifact and forbidden-content checks. Repeating the temporary corruption test after deleting the Authoring `capability` module and its contract still produced zero verification errors with only 15 modules and 15 contracts remaining.
- Second mentor decision: Rejected again on 2026-08-11. `67708e5` was not accepted as the dependency baseline.
- Direct remediation: The mentor implemented the fixed 22-module catalog, 92 substantive normative rules, 25 transitions, 22 stable module errors and all 75 admitted contracts. Every contract has a typed JSON Schema 2020-12 payload, two examples, producer/consumer usage, owning protocol/module, executable verifier reference and evidence placeholder. The verifier owns independent expected module, rule, transition and contract catalogs.
- Direct remediation commit: `88a8440fb919c746ef28bfc797817a7dc7045f76` on `workers/worker-001-protocol-source-rebuild`.
- Direct remediation evidence: Both verifier entry points pass; 10 deliberate-corruption tests pass; two empty rebuilds and the checked-in database share SHA-256 `F66E17DC3ED65F553B0BA2D1A34B7810A765CDBBCD93037AB5EA02537632FF77`; SQL proves 1 source, 4 protocols, 22 modules, 92 rules, 25 transitions, 22 errors, 75 contracts, 150 examples, 75 evidence placeholders, zero migration rows and zero coverage failures.
- Review: TruffleHog passed. Autoreview refused the full commit because it contains the normative SQLite binary. A text-only review projection was attempted without changing the delivered commit, but the Codex reviewer subprocess failed in its isolated temporary PATH before returning findings. Manual source review, digest coverage checks, deterministic rebuild and corruption tests found no remaining blocker.
- Current mentor acceptance: Accepted on 2026-08-11. Integrated into protocol repository `main` with non-fast-forward merge `fc08310`, verified again after merge and removed the clean merged worktree. The worker branch remains for audit. Nothing was pushed.

The failed worker deliveries remain recorded above as review history. No further
remediation command is active for worker 001.

### worker-002-authoring-core-implement

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-003-distribution-core-implement

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-004-runtime-core-implement

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-005-dr-runtime-implement

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-006-backend-boundary-align

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-007-product-surfaces-align

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-008-viewer-context-clean

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-009-conformance-gates-build

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-010-registry-snapshot-publish

- Prompt issued: Pending
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

## Worker Cards

### worker-001-protocol-source-rebuild

Name and objective: `worker-001-protocol-source-rebuild` - build the clean authoritative four-layer protocol source and SQLite model.

Status: `accepted`

Allowed write paths and explicit exclusions: write only inside the protocol repository `protocol-source/**`. Do not write the main product, DR, viewer, tests, user planning files, or any generated `.data/` content.

Dependencies and branch: none; branch `workers/worker-001-protocol-source-rebuild` in the protocol repository.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-protocol-source-worker-001-protocol-source-rebuild"
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow\protocol-source" worktree add $worktree -b "workers/worker-001-protocol-source-rebuild"
$prompt = @'
You are worker-001-protocol-source-rebuild. Build the authoritative CartridgeFlow protocol repository as a clean-room new system. Write only inside this worktree's protocol repository. Do not modify the main product, DR, viewer, tests, user planning files, or generated data.

Objective: replace the mixed protocol-source design with one clean SQLite source containing only the new four-layer system: CF-FOUNDATION, CF-AUTHORING, CF-DISTRIBUTION and CF-RUNTIME. The future AI must not see any previous protocol identity, body, history, archive, migration row or legacy source. Start from a fresh database/schema or a clean rebuild; do not delete the old database in another location and do not copy old rows into the new database. Keep the four-layer model, but expand it into modules, normative rules, state transitions, error codes, data contracts, examples, implementation evidence and readable specifications based on the current business target. Existing task context is: Intent Studio expresses semantic intent and unresolved capability gaps; Capability Workshop creates executable Flow capabilities; recursive composition freezes exact dependencies; distribution owns package/integrity/trust/install; runtime owns host negotiation/execution/recovery/artifacts/delivery.

Own the SQLite schema, source publication tooling, clean-source verification, release metadata and authoritative protocol content. There must be exactly one new source in the final database. Do not preserve a legacy table as an active or browsable source. Future-version evolution may have generic schema support, but this initial database must contain no previous-system migration records. Every formal data contract needs JSON Schema 2020-12, a valid example, an invalid example, producer/consumer bindings, semantic rules and an implementation-evidence placeholder. Every module needs scope, non-scope, rules, state/error behavior and owner.

Acceptance tests: run the source verifier; run publication/update tooling tests; query the database to prove one source, four protocols, complete module/rule/contract/example/evidence coverage, no forbidden previous identities or history rows; run any repository test suite relevant to your changes. Keep source commits immutable and do not push from the worker unless separately instructed. Commit only this worker's allowed paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Fresh source database opens with foreign keys and integrity checks enabled.
- Only the new source and four new protocol releases are queryable.
- Modules, rules, state transitions, errors, contracts, examples and evidence are first-class records.
- No previous protocol identity, archive, history or migration row is in the new database.
- Source verification, publication tests and a clean commit report pass.

### worker-002-authoring-core-implement

Name and objective: `worker-002-authoring-core-implement` - implement the new authoring, Flow, data-binding and recursive composition contracts in Python core.

Status: `planned`

Allowed write paths and explicit exclusions: write only the listed authoring paths: `src/core/protocol/authoring_contract.py`, `capability_cartridges.py`, `capability_registry.py`, `creator_templates.py`, `flow_contract.py`, `tool_plan.py`, `trusted_node_recipes.py`, `tuning.py`, `src/core/lab/**`, and the selected authoring files under `src/core/studio/` (`authoring_service.py`, `capability_cartridges.py`, `creator_runtime_bridge.py`, `resource_catalog.py`, `resource_resolver.py`, `trusted_node_presets.py`, `tuning_repository.py`). Exclude the protocol source/database, shared data-contract engine owned by worker 004, Base manifest, distribution, runtime, backend, frontends, DR and tests.

Dependencies and branch: worker-001 accepted and its protocol source commit integrated/available; branch `workers/worker-002-authoring-core-implement`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-002-authoring-core-implement"
git worktree add $worktree -b "workers/worker-002-authoring-core-implement"
$prompt = @'
You are worker-002-authoring-core-implement. Implement only the new CF-AUTHORING behavior in the listed Python core paths. The authoritative contract catalog is supplied by the accepted protocol-source worker; do not invent incompatible IDs and do not edit the source database.

Implement the current target business: semantic intent projects and nodes may remain unresolved; AI capability matches are reviewable proposals; capability definitions have precise ports, fields, dependencies, trust scope and immutable releases; Flow has nodes, edges, execution plans, decisions and interactions; data bindings and Store boundaries are explicit; settings, UI, model/tool/resource bindings and package-owned extensions are declared; recursive composition resolves exact versions, rejects cycles and materializes deterministic namespaces while preserving provenance. Replace old protocol execution paths with the new contract adapters. Do not carry previous identities into new payloads or error messages.

Do not edit tests in this worker; run the existing focused authoring/lab/studio tests and report failures. Do not touch dirty user paths outside your allowlist. Commit only the listed implementation paths after a diff-scope check.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Intent, capability, Flow, data-binding and composition code consumes only the new catalog.
- Unresolved intent remains editable and cannot be falsely published.
- Recursive composition is deterministic, cycle-safe and provenance-preserving.
- Authoring-focused tests pass without changing excluded files.

### worker-003-distribution-core-implement

Name and objective: `worker-003-distribution-core-implement` - implement new package, integrity, trust, installation and exposure behavior.

Status: `planned`

Allowed write paths and explicit exclusions: `src/core/cartridge/**` except `runner.py`; `src/core/protocol/release_builder.py`, `release_envelope.py`, `release_signing.py`, `certification.py`, `artifact_store.py`; `src/core/studio/release.py`, `portability.py`, `hygiene.py`. Exclude protocol source/database, authoring core, runtime state, backend, frontends, DR and tests.

Dependencies and branch: workers 001 and 002 accepted; branch `workers/worker-003-distribution-core-implement`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-003-distribution-core-implement"
git worktree add $worktree -b "workers/worker-003-distribution-core-implement"
$prompt = @'
You are worker-003-distribution-core-implement. Implement only the new CF-DISTRIBUTION package and trust boundary in the listed paths. Use the accepted clean protocol catalog; do not edit protocol SQLite or tests.

Implement package manifest/content ownership, deterministic dependency locks, safe paths and package members, content and manifest digests, signature payloads, publisher/trust scopes, import and installation preflight, atomic installation, upgrade/rollback boundaries, public experience and delivery declarations. A signature is not sufficient for trust or compatibility. Packages must not contain credentials, user data or run history. Remove previous protocol identities from active behavior in these paths, but do not edit files outside your allowlist.

Run focused cartridge, release, signing, certification and portability tests. Do not change test files in this worker. Commit only allowed implementation paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Package members, paths, dependencies and digests are deterministic and fail closed.
- Import/install checks integrity, trust, compatibility and resources before activation.
- Signature, trust, installation and exposure behavior use only new contracts.
- Focused distribution tests pass and the worker diff stays within scope.

### worker-004-runtime-core-implement

Name and objective: `worker-004-runtime-core-implement` - implement new Python host, execution, recovery, artifact and delivery semantics.

Status: `planned`

Allowed write paths and explicit exclusions: `src/core/runtime/**`, `src/core/cartridge/runner.py`, `src/core/protocol/base_manifest.py`, `compatibility.py`, `data_contracts.py`, `report.py`, `release_catalog.py`. Exclude protocol source/database, authoring, distribution, backend, frontends, DR and tests.

Dependencies and branch: worker-001 accepted; worker-003 package boundary accepted; branch `workers/worker-004-runtime-core-implement`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-004-runtime-core-implement"
git worktree add $worktree -b "workers/worker-004-runtime-core-implement"
$prompt = @'
You are worker-004-runtime-core-implement. Implement only the new CF-RUNTIME, shared data-contract validation engine and Base selection behavior in the listed Python paths. Do not edit protocol SQLite.

Implement host profile/target negotiation, compatibility findings, immutable-run binding, scheduler/execution state, node state transitions, interaction waits, stable errors, checkpoint creation, retry/cancel/recovery safety, artifact ownership and true delivery results. A run is not delivered merely because a file was generated; the declared data chain and meaningful output must be present. Python behavior must be expressible in the new runtime contracts and must fail closed on missing or ambiguous declarations. Remove active execution dependencies on previous protocol identities in your allowlist.

The main worktree has unrelated uncommitted changes; your branch starts from the committed baseline. Do not attempt to reconcile or reset the main worktree. Run focused runtime, runner, compatibility and recovery tests without editing tests. Commit only allowed implementation paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Host negotiation rejects unsupported targets and reports stable findings.
- Execution states, interactions, errors and recovery are finite and fail closed.
- Checkpoints cannot repeat unsafe side effects and delivery requires real output.
- Focused Python runtime tests pass within the allowed paths.

### worker-005-dr-runtime-implement

Name and objective: `worker-005-dr-runtime-implement` - align the independent Go Desktop Runner with the new host/runtime contracts.

Status: `planned`

Allowed write paths and explicit exclusions: in the independent DR repository, `shell/go/internal/runtimeprofile/**`, `shell/go/internal/verify/**`, `shell/go/internal/runner/**`, `shell/go/internal/scheduler/**`, `shell/go/internal/store/**`, and tests in those packages. Exclude the main repository, protocol source, Python code, frontend, and unrelated Go packages.

Dependencies and branch: workers 001 and 004 accepted; branch `workers/worker-005-dr-runtime-implement` in the DR repository.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-DR-worker-005-dr-runtime-implement"
git -C "C:\_HOLOLAB\code\CF WS\CartridgeFlow\DR" worktree add $worktree -b "workers/worker-005-dr-runtime-implement"
$prompt = @'
You are worker-005-dr-runtime-implement in the independent DR repository. Implement only the new CF-RUNTIME host, verification, execution, recovery and delivery behavior in the listed Go packages. The main repository's protocol source is external to this worktree; use the accepted new contract definitions as the authority and do not add compatibility for the previous protocol identities.

Keep Python and Go host negotiation semantically equivalent: exact target schema, protocol generation, state types, UI mode, stable finding/error codes, run state transitions, checkpoint/recovery rules, artifact ownership and delivery outcomes. Preserve platform-specific process behavior. Do not edit unrelated packages or the main repository. Run gofmt, go vet ./... and go test ./... -count=1. Commit only the allowed DR paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Go host/runtime behavior matches the new contract examples and Python report semantics.
- `gofmt`, `go vet ./...` and `go test ./... -count=1` pass.
- No previous protocol identity or compatibility branch is introduced.

### worker-006-backend-boundary-align

Name and objective: `worker-006-backend-boundary-align` - align FastAPI models and routes with the new protocol contracts.

Status: `planned`

Allowed write paths and explicit exclusions: `src/backend/api_models.py`, `src/backend/main.py`. Exclude all core implementation, protocol source/database, DR, frontend, tests and documentation.

Dependencies and branch: workers 001-004 accepted; branch `workers/worker-006-backend-boundary-align`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-006-backend-boundary-align"
git worktree add $worktree -b "workers/worker-006-backend-boundary-align"
$prompt = @'
You are worker-006-backend-boundary-align. Align only the FastAPI request/response models and routes in the two allowed backend files with the accepted new protocol contracts.

Preserve the single same-origin application and the existing Intent/Capability product boundary. Validate incoming data at API boundaries, return stable new error envelopes, keep unresolved intent editable, require explicit capability verification before publication, and expose new host/package/runtime results without leaking internal implementation or previous protocol identities. Do not change core modules, UI, DR, database or tests. The main worktree has unrelated uncommitted changes; do not touch them from the worker worktree and report any integration assumptions.

Run the focused API tests and a minimal health/openapi smoke check. Commit only the two allowed files.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- API models and routes use only new contract identities and stable failure envelopes.
- Intent, capability publication, package and runtime routes preserve product boundaries.
- Focused API tests and smoke checks pass; no excluded path changes.

### worker-007-product-surfaces-align

Name and objective: `worker-007-product-surfaces-align` - align Intent Studio and Capability Workshop with the new protocol language and payloads.

Status: `planned`

Allowed write paths and explicit exclusions: `src/intent-studio/**`, `src/capability-workshop/**`. Exclude backend, Python core, protocol source/database, DR, tests outside frontend-local test files and documentation.

Dependencies and branch: workers 001, 002 and 006 accepted; branch `workers/worker-007-product-surfaces-align`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-007-product-surfaces-align"
git worktree add $worktree -b "workers/worker-007-product-surfaces-align"
$prompt = @'
You are worker-007-product-surfaces-align. Align only Intent Studio and Capability Workshop with the accepted new protocol model.

Intent Studio must expose user goals, semantic nodes, editable fields, source review, capability proposals, rejection and unresolved gaps without exposing technical Flow topology, executor bindings, permissions or runtime controls. Capability Workshop must expose executable Flow design, typed ports, settings, tools/resources, validation, trust and immutable publication. Both surfaces must use backend payloads from the new contracts and must not show previous protocol identities. Preserve the same-origin boundary and do not redesign unrelated UI. The main worktree has user UI changes; your isolated branch starts from the committed baseline, and your report must identify any likely integration conflicts.

Run frontend build and test commands for both surfaces. Commit only allowed frontend paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Both frontend surfaces use new payload identities and preserve their distinct responsibilities.
- Unresolved semantic nodes remain editable; technical implementation remains in the workshop.
- Both frontend build/test suites pass and no excluded files change.

### worker-008-viewer-context-clean

Name and objective: `worker-008-viewer-context-clean` - make the browser and AI-facing project guidance expose only the new protocol system.

Status: `planned`

Allowed write paths and explicit exclusions: `config/protocol-viewer/**`, `view-protocols.bat`, `AGENT.md`, `README.md`, and `docs/development/FILE_INVENTORY.md` if it exists. Exclude SQLite contents and lock files, product implementation, DR, tests and user planning files.

Dependencies and branch: workers 001 and 010 accepted; branch `workers/worker-008-viewer-context-clean`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-008-viewer-context-clean"
git worktree add $worktree -b "workers/worker-008-viewer-context-clean"
$prompt = @'
You are worker-008-viewer-context-clean. Update only the protocol browser, launcher and AI-facing engineering guidance in the allowed paths.

The browser must show a simple tree: four layers -> business domains -> protocol modules -> rules/data contracts/evidence, with the selected content on the right. It must not show archived protocol records, historical migration graphs, old sources or old identities. The launcher must open the local browser automatically and reuse the server when it is already running. AGENT.md and README.md must teach only the new protocol workflow, SQLite source/published-copy boundary and validation gates. Do not edit the database or lock; consume the accepted product snapshot. Preserve unrelated product decisions and do not add decorative UI.

Run the viewer tooling tests and real browser smoke checks at desktop and mobile sizes. Commit only allowed paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Browser and guidance expose only new layers/modules/contracts and no old context.
- The browser can open a selected rule or contract directly and return to the tree.
- Desktop/mobile smoke checks and viewer tests pass.

### worker-009-conformance-gates-build

Name and objective: `worker-009-conformance-gates-build` - build the fail-closed rule, contract, state, error, cross-language and end-to-end gates.

Status: `planned`

Allowed write paths and explicit exclusions: `scripts/tests/**`, `scripts/validate_*.py`, `scripts/audit_*.py`, `scripts/run_conformance.py`. Exclude product implementation, protocol source/database, product snapshot/lock, viewer, docs, DR implementation and user files.

Dependencies and branch: workers 001-008 and 010 accepted; branch `workers/worker-009-conformance-gates-build`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-009-conformance-gates-build"
git worktree add $worktree -b "workers/worker-009-conformance-gates-build"
$prompt = @'
You are worker-009-conformance-gates-build. Own all new verification and test changes. Do not edit product implementation or protocol database.

Build fail-closed checks for: four-layer/module completeness; rule and contract identity/version uniqueness; Schema 2020-12 and valid/invalid examples; producer/consumer and implementation evidence; state transition and error-code coverage; Base support; Python/Go equivalence; package integrity/trust/install; Intent-to-capability handoff; recursive composition; runtime delivery; browser-facing source cleanliness. Add deliberate-corruption tests that prove missing modules, contracts, evidence, validators, states, errors or old identities fail. Update the conformance runner and governance audit so no old protocol context can pass. Use the new product snapshot after worker 010.

Run targeted tests first, then the full Python suite and all available frontend/Go integration commands as read-only evidence. Commit only tests and validation scripts in the allowlist.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Deliberate protocol/code corruption fails with stable findings.
- Full conformance proves current business gates, not historical migration counts.
- Python, frontend and available cross-language integration evidence is recorded.
- No excluded files change.

### worker-010-registry-snapshot-publish

Name and objective: `worker-010-registry-snapshot-publish` - publish the accepted clean protocol source into the product read-only SQLite and lock it.

Status: `planned`

Allowed write paths and explicit exclusions: `config/protocol/**`, `scripts/update_protocol_registry.py`. Exclude authoritative protocol source contents, product implementation, viewer, tests, DR and docs.

Dependencies and branch: worker-001 accepted; branch `workers/worker-010-registry-snapshot-publish`.

Worktree setup command and launch command:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-010-registry-snapshot-publish"
git worktree add $worktree -b "workers/worker-010-registry-snapshot-publish"
$prompt = @'
You are worker-010-registry-snapshot-publish. Publish only the accepted clean protocol-source commit into the product's read-only SQLite snapshot and lock files.

The product snapshot must contain exactly one new protocol source, four new protocol releases, the complete new modules/contracts/rules/states/errors/examples/evidence and no previous protocol source, identity, archive or migration record. The updater must require a clean, committed, published authoritative source and must verify source/database logical digests. Do not edit the authoritative source itself; do not edit product code, viewer or tests. Run updater, snapshot integrity and lock verification tests. Commit only the allowed paths.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

Acceptance criteria with observable evidence:

- Product snapshot has one new source and no previous protocol material.
- Database SHA, logical digest and source commit lock agree.
- Updater rejects dirty or unpublished authoritative sources.
- Only allowed snapshot/updater paths change.

## Mentor Acceptance and Integration Checklist

The mentor, not a worker, owns integration into the dirty main worktree.

- [ ] Obtain the exact Worker Delivery Report from every worker.
- [ ] Verify each commit exists on its declared branch and changes only allowed paths.
- [ ] Verify the declared dependency baseline is an ancestor.
- [ ] Record acceptance in this register before merging.
- [ ] Preserve the user's currently dirty files and resolve conflicts explicitly.
- [ ] Integrate the protocol source repository before dependent workers.
- [ ] Integrate the product snapshot only from the accepted source commit.
- [ ] Integrate code workers one at a time with non-fast-forward merges.
- [ ] Run targeted evidence after each accepted integration.
- [ ] Run full Python, frontend, Go, browser and static-scan gates at the end.
- [ ] Confirm the active workspace and AI guidance contain no previous protocol context.
- [ ] Remove accepted worker worktrees only after clean status and merged-commit checks.
- [ ] Do not remove a dirty, unaccepted, failed or unmerged worktree.

## Update Log

| Time | Update |
| --- | --- |
| 2026-08-11 Asia/Shanghai | Register created for clean-room protocol rebuild; no workers started. |
| 2026-08-11 10:19 Asia/Shanghai | Reviewed worker 001 commit `f9305813`; scope and declared tests passed, but delivery was rejected because the 16-module catalog does not implement the accepted 22-module architecture and a temporary missing-module-plus-contract corruption still passed verification. No merge, push, or cleanup performed. |
| 2026-08-11 Asia/Shanghai | Reviewed worker 001 follow-up `67708e5`; row-quality verification improved, but the source remained at the same 16 modules/contracts and the missing-slice corruption still passed. Rejected again; no merge, push, cleanup, or dependent-worker start. |
| 2026-08-11 11:44 Asia/Shanghai | Mentor directly completed worker 001 at `88a8440`, proved the 22-module/75-contract catalog and fail-closed corruption gates, and integrated it into protocol `main` as `fc08310`. Post-merge verification passed; no push performed. |
| 2026-08-11 11:44 Asia/Shanghai | Removed the clean merged worker 001 worktree after verifying `88a8440` is an ancestor of protocol `main`; retained the branch and commits. |
