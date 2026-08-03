# Worker 303 API Remediation

Run this from PowerShell:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio"

git -C $worktree status --short
git -C $worktree merge main

$prompt = @'
Continue Worker 303 from candidate
`02ceea083b081953fffe7c582ea480e6bce3aaf6`.

First merge current main. The current branch's merge base is `ae9205c`, so it
does not contain accepted Worker 306 (`CF-FARP@1.3`, `CF-TUNING@1.2`, and the
Creator contract). Do not rebase or rewrite history. If the merge conflicts,
preserve both sides and resolve only the conflict; do not discard main or the
existing Creator Studio work.

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

The existing API client and fetch-mocked coverage are a base, but this follow-up
must fix all remaining acceptance blockers:

1. Source editing
   - Add creator-language source edit controls for existing sources.
   - Use `update_source` through proposal -> preview -> accept.
   - Preserve source identity/kind and create a valid safe digest/reference for
     the edited source.
   - Keep client validation for HTTPS-only, no URL user-info, no sensitive query
     keys, and no local paths.

2. Preview impact
   - Extend the API client types to retain the service's preview impact payload.
   - Render the creator-safe impact summary and changed steps/sources before
     accepting an AI proposal or direct edit. Do not only show operation IDs.

3. Frozen AI proposals
   - When a selected AI proposal affects an active frozen step, construct and
     send the exact `freeze_revision` from Creator projection for both preview
     and accept.
   - If a proposal cannot be safely authorized from creator-visible facts,
     preserve the server rejection and explain it in creator language. Never
     silently mutate, downgrade, or bypass frozen state.

4. Browser regression
   - Add a reproducible native Python Playwright workflow under
     `src/creator-studio/test/` without adding unnecessary npm dependencies.
   - It must mock the Creator HTTP API and verify the browser performs source
     update, AI proposal -> preview impact -> partial accept, frozen-step
     revision handling, reversal conflict rendering, design readiness, and
     compile-candidate gating.
   - It must create a screenshot as test output but do not commit generated
     screenshots. Document the invocation in the package README or test file.

5. Tests
   - Extend Vitest fetch-mocked tests for update_source, preview impact, and
     frozen AI proposal request bodies.
   - Run the browser workflow through the local Vite server.
   - Re-run `npm ci`, `npm test`, `npm run build`, and `git diff --check`.

Keep Creator Studio independent and API-only. Do not claim a compile candidate
is signed or running. Add a normal follow-up commit; do not amend or rebase.
Finish with a clean worktree.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@

codex -C $worktree $prompt
```
