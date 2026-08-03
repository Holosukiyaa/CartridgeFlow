# Worker 303 Resume Instruction

Run this from PowerShell:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio"

git -C $worktree status --short
git -C $worktree merge main

$prompt = @'
Continue Worker 303. The current branch contains the static prototype
`3e275f9`, and current main includes Worker 306's `CF-FARP@1.3`,
`CF-TUNING@1.2`, and Creator API contract. Do not rewrite history. Ensure
`git merge main` succeeds before editing.

Allowed writes:
- src/creator-studio/**

Excluded:
- src/frontend/**
- src/backend/**
- src/core/**
- protocol/**
- config/**
- src/developer-console/**
- demos/**
- root dependency files
- PLAN.md
- MENTOR_WORKERS.md

Goal:
Replace the local hard-coded prototype with an independent, API-driven Creator
Studio. The browser must use HTTP APIs for authoring sessions; React state may
cache Creator projections but is not the accepted-design source of truth.

Use the current Creator API:
- POST/GET `/api/creator/authoring-sessions`
- POST `.../ai-proposals`
- POST `.../proposals`
- POST `.../proposals/{proposal_id}/preview`
- POST `.../proposals/{proposal_id}/accept`
- POST `.../proposals/{proposal_id}/reject`
- POST `.../revisions/{acceptance_id}/reverse`
- POST `.../freeze`
- GET `.../design-checks`
- POST `.../generation-readiness`
- POST `.../compile-candidate`

Read the current `src/backend/main.py`, `src/backend/api_models.py`, and
`src/core/studio/authoring_service.py` for the actual request and response
shapes. Do not guess fields.

Requirements:
1. Add a clear API client supporting `VITE_API_BASE_URL` and consistent API
   error handling.
2. Create and restore sessions. Render intent, sources, steps, relations,
   freezes, history, blocked findings, and readiness from Creator projection.
3. Add, edit, and remove sources only through proposal -> preview -> accept.
   Never send credentials, sensitive query values, URL user-info, or local
   paths.
4. Use service revisions for AI proposals, rejection, partial acceptance, and
   requests for AI modification. Displayed accepted counts must exactly match
   selected IDs and returned `accepted_change_ids`.
5. Route direct edits and manual-canvas step/connection actions through the
   same proposal -> preview -> accept transaction path.
6. For frozen-step edits, construct `freeze_revision` from active freezes or
   present the server rejection. Never silently downgrade frozen state.
7. Reverse accepted revisions using their history acceptance IDs. Render stable
   conflict errors; never fabricate a successful undo.
8. Gate compilation on design checks and generation readiness. Generation calls
   only compile-candidate and must describe the result as a handoff candidate,
   not a signed or executing cartridge.
9. Keep a creator-language manual canvas with real, testable add-step and
   connect-step operations. Hide protocol, model, tool, and executor terms.

Testing:
- Use fetch mocks to cover session creation/loading, source mutation, AI
  proposal, preview, partial acceptance, frozen edits, reversal, design checks,
  readiness, and compile candidates.
- Assert HTTP method, path, request body, and UI projection updates.
- Add a Playwright browser workflow and screenshot: source entry -> AI proposal
  -> partial acceptance -> freeze -> blocker resolution -> design check ->
  compile candidate. Assert expected `/api/creator/...` requests.
- Run `npm ci`, `npm test`, `npm run build`, and `git diff --check`.

Create a normal follow-up commit only. Do not amend or rebase. End with a clean
worktree.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@

codex -C $worktree $prompt
```
