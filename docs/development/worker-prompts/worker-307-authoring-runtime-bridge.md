# Worker 307 Authoring Runtime Bridge

Run this from PowerShell:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-307-authoring-runtime-bridge"

git worktree add $worktree -b "workers/worker-307-authoring-runtime-bridge"

$prompt = @'
You are worker-307-authoring-runtime-bridge. Implement the missing explicit
backend/core bridge from a current, accepted, frozen Creator revision to a
deterministic CF-FARP Root Flow and a signed CF-CRE package. Reuse the existing
CartridgeFlow release/signing infrastructure; do not create a parallel archive
format or claim any production runtime execution.

Allowed writes:
- src/backend/**
- src/core/studio/**
- directly related src/core/cartridge/**
- scripts/tests/api/**
- scripts/tests/studio/**
- scripts/tests/integration/**
- directly related maintenance documentation

Excluded:
- protocol/**
- config/**
- src/creator-studio/**
- src/developer-console/**
- src/frontend/**
- demos/**
- root dependency files
- PLAN.md
- MENTOR_WORKERS.md

First inspect the existing Creator compile-candidate/readiness service, the
CF-FARP compiler/validator, and the existing CF-CRE package/signing endpoints.
Use their established API and error patterns. Do not mutate a Creator session
as a side effect of compilation or packaging. Do not amend, rebase, or rewrite
history.

Requirements:

1. Add an explicit creator-facing backend operation that takes a known
   compile candidate for a session/revision and materializes the accepted
   semantic steps and relationships into a valid deterministic CF-FARP
   `root.flow.json`, then produces a signed CF-CRE handoff package through the
   existing signer/package pipeline.
2. Accept only current revision facts that are accepted, design-ready,
   unblocked, and backed by applicable valid freeze facts. Reject stale
   revisions, candidate/session mismatch, missing or invalid freezes, blocked
   design state, and incompatible topology with stable machine-readable errors.
   A failed request must not leave a package or a mutated creator revision.
3. Retain auditable public lineage in the package only as safe identifiers and
   digests for the accepted revision, freeze snapshots, and compile candidate.
   Never place prompts, chat, source content/URLs, Creator session records,
   developer repositories, frontend state, credentials, tokens, cookies,
   authorization data, or local paths into Root Flow, public payloads, archive
   members, logs, or error responses.
4. Use the existing CF-CRE signing and verification path. The response may
   describe a signed handoff artifact, but must not state that it is installed,
   running, or production-executed.
5. Add direct service/API/integration tests proving the positive path reaches
   materialized `root.flow.json`, a signed archive, and independent signature
   verification. Prove deterministic or controlled-idempotent output for the
   same immutable inputs. Add negative tests for every condition in item 2,
   tampered archive/signature, and private-state leakage.
6. If the released protocol or CF-CRE envelope cannot represent necessary
   public lineage without ambiguity, stop and report the exact required
   protocol/governance change. Do not silently change published protocol files.

Run targeted service/API/integration tests, protocol governance and full
conformance where applicable, plus `git diff --check`. Finish with a clean
worktree and one normal commit.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@

codex -C $worktree $prompt
```
