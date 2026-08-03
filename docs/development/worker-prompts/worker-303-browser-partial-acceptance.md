# Worker 303 Browser Partial-Acceptance Fix

Run this from PowerShell:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio"

git -C $worktree status --short

$prompt = @'
Continue Worker 303 from candidate
`b384a33ec8ca70630eecc37738d6ef10783567b6`.

Do not rebase, amend, merge, or rewrite history. The branch is already based
on the accepted Worker 306 contract. Make one small normal follow-up commit.

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

One acceptance criterion remains unmet: `test/browser_workflow.py` must prove
partial acceptance in a real browser, not only in Vitest.

Update the mocked AI proposal in the Python Playwright workflow to contain at
least two distinct changes. In the browser, deselect one proposal change,
preview the remaining selected change, and accept it. Assert that both preview
and accept request bodies contain exactly the remaining selected change ID, and
that the acceptance response/UI only reports that selected change. Keep the
existing coverage for source update, preview impact, frozen `freeze_revision`,
reversal conflict, design checks, readiness, compile-candidate gating, and the
ignored screenshot.

Run:
- npm ci
- npm test
- npm run build
- python test/browser_workflow.py
- git diff --check

Do not modify package dependencies. Finish with a clean worktree.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@

codex -C $worktree $prompt
```
