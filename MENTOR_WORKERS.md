# Mentor Worker Register

Project: CartridgeFlow AI-Assisted Authoring
Repository root: `C:\_HOLOLAB\code\CF WS\CartridgeFlow`
Active delivery: `creator-ai-authoring-2026-08`
Last updated: 2026-08-03 13:24 +08:00
Mentor: Codex `/root` using `mentor-orchestrator`

## Active Baseline

`PLAN.md` revision `creator-ai-authoring-2026-08-r1` is the frozen product and
delivery baseline. CartridgeFlow owns
creator authoring and a separate developer console. The runtime project owns
production execution. AI proposals are reviewable revision transactions;
creators progressively freeze semantic steps into versioned recipe instances
and CF-FARP topology before generating a cartridge.

## Workers

| Worker | Status | Objective | Allowed write paths | Exclusions | Dependencies | Branch | Worktree | Acceptance evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| worker-201-uxp-contract | rejected | Superseded runtime-oriented User Experience Plan contract. | Historical branch only; no further writes authorized. | Main integration and all new delivery work. | None | `workers/worker-201-uxp-contract` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-201-uxp-contract` | Clean branch at `d57df6a`; rejected because product direction changed before merge. |
| worker-301-authoring-contract | planned | Version portable blueprints, instances, AI change sets and freeze semantics while preserving FARP topology ownership. | Next protocol releases, catalog/governance, Base declarations, `src/core/protocol/**`, direct tests/evidence. | Backend, frontends, demos, dependencies, mentor files. | None | `workers/worker-301-authoring-contract` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-301-authoring-contract` | Pending |
| worker-302-authoring-service | planned | Implement revisioned design sessions, AI proposal transactions, acceptance/undo, freezing and compilation APIs. | Backend, studio/cartridge core, authoring LLM adapters, direct service/API tests. | Protocol/config, frontends, demos, dependencies, mentor files. | Accepted and merged worker-301 | `workers/worker-302-authoring-service` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-302-authoring-service` | Pending |
| worker-303-creator-studio | planned | Build the AI-first semantic Creator Studio and secondary manual canvas. | `src/frontend/**` and its own tests/dependencies. | Backend/core/protocol/config, Developer Console, demos, mentor files. | Accepted and merged worker-302 | `workers/worker-303-creator-studio` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio` | Pending |
| worker-304-developer-console | planned | Build an independent, API-connected full engineering and tuning frontend. | New `src/developer-console/**` package and its own tests/dependencies. | Existing frontend, backend/core/protocol/config, demos, root dependencies, mentor files. | Accepted and merged worker-302 | `workers/worker-304-developer-console` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-304-developer-console` | Pending |
| worker-305-authoring-integration | planned | Own final cross-surface evidence and minimal signed-package runtime handoff updates. | Runtime toolkit, new integration tests, directly related maintained docs. | Product implementation, dependencies, mentor files. | Accepted and merged workers 303 and 304 | `workers/worker-305-authoring-integration` | `C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-305-authoring-integration` | Pending |

Workers 303 and 304 may run in parallel only after Worker 302 is accepted and
merged. No active Worker may merge or cherry-pick Worker 201.

## Worker Reports

### worker-201-uxp-contract

- Prompt issued: Issued under superseded delivery `uxp-2026-08`.
- Changed files: Not accepted or enumerated into the active delivery.
- Commit: `d57df6a` tip; six branch-only commits, unmerged.
- Tests: Worker report not received in the active mentor thread.
- Risks or follow-up: Implements the rejected ordinary-user runtime UXP model.
- Mentor acceptance: `rejected` due to changed product objective, not due to a
  code-quality judgment. Preserve worktree pending user-approved cleanup.

### worker-301-authoring-contract

- Prompt issued: Planned; exact self-contained prompt and commands in `PLAN.md`.
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-302-authoring-service

- Prompt issued: Planned; wait for accepted/merged worker-301.
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-303-creator-studio

- Prompt issued: Planned; wait for accepted/merged worker-302.
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-304-developer-console

- Prompt issued: Planned; wait for accepted/merged worker-302.
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-305-authoring-integration

- Prompt issued: Planned; wait for accepted/merged workers 303 and 304.
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

## Update Log

| Time | Update |
| --- | --- |
| 2026-08-03 10:16 +08:00 | Original runtime-oriented UXP delivery registered. |
| 2026-08-03 11:52 +08:00 | Product direction corrected: Creator Studio is AI-assisted authoring, Developer Console is a separate frontend, and production runtime remains external. Worker 201 rejected before merge; delivery 301-305 planned. |
| 2026-08-03 13:24 +08:00 | Baseline revision `creator-ai-authoring-2026-08-r1` frozen before Worker 301 starts. Root engineering documents aligned to the three-surface product boundary. |
