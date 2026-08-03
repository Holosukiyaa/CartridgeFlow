# Worker 305 Final Handoff Evidence

Run this from PowerShell:

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS\CartridgeFlow"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-305-authoring-integration"

git -C $worktree status --short
git -C $worktree merge main

$prompt = @'
Continue worker-305-authoring-integration from candidate
`00fb57b627fcbf8c8c1948e7d2a282dbf6faa7c7`.

First merge current main. It includes accepted Worker 307 as
`9498f11f9b7347b3cb36dad6ce7800902bd836f4`, which provides the supported
Creator revision -> Root Flow -> signed CF-CRE handoff bridge. Do not rebase,
amend, or rewrite history. Preserve both sides of any merge conflict.

Allowed writes:
- demos/runtime-developer-toolkit/**
- new integration/acceptance tests
- directly related maintenance documentation describing the three-surface boundary

Excluded:
- protocol/**
- config/**
- src/core/**
- src/backend/**
- src/creator-studio/**
- src/developer-console/**
- src/frontend/**
- root dependency files
- PLAN.md
- MENTOR_WORKERS.md

Implement final evidence only. Do not repair product code outside this Worker.

1. Use the public Creator API flow to create a valid authoring session with a
   source reference and semantic steps, accept a relationship, freeze all
   steps, obtain the current compile candidate, and invoke the Worker 307
   runtime-handoff endpoint with its expected revision and candidate.
2. Fetch the returned signed package through its public package URL. Verify it
   independently with the runtime developer toolkit's trusted-signature path
   and validate its Root Flow. Do not substitute an existing sample package.
3. Prove the generated archive excludes chat, prompts, Creator session records,
   developer repository data, frontend state, credentials, source URLs, and
   local paths. Confirm the response/package says only signed handoff and never
   claims installation, execution, or a running cartridge.
4. Keep existing negative boundary tests. Add acceptance evidence that fails if
   the API handoff is blocked, unsigned, unverifiable, or leaks private facts.
5. Run runtime toolkit checks/tests, both standalone frontend builds and tests,
   full conformance, and `git diff --check`.

Finish with a clean worktree and a normal follow-up commit.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@

codex -C $worktree $prompt
```
