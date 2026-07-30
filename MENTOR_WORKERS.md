# Mentor Worker Register

Project: CartridgeFlow
Repository root: `C:\_HOLOLAB\code\CF WS\CartridgeFlow`
Last updated: 2026-07-30 Asia/Shanghai
Mentor: Codex mentor-orchestrator

## Delivery Plan

Deliver `ENG-021` with parallel lanes. Establish a clean baseline containing the current planning work before creating worktrees; the root worktree is currently dirty and new worktrees otherwise start from `758cf3f` without that work.

1. Start `worker-001-resource-contracts` and `worker-003-engineering-canvas` at the same time. Their allowed write paths do not overlap.
2. `worker-002-external-mcp-detail` starts when worker 001's accepted backend contract is in its base branch.
3. `worker-004-engineering-integration` starts when workers 001, 002, and 003 are accepted and present in its base branch. It owns only the integration seam and final E2E evidence.

No worker may merge another worker branch. The user explicitly approves any merge or rebase used to prepare the next worker's base branch.

## Workers

| Worker | Status | Objective | Allowed write paths | Exclusions | Dependencies | Branch | Worktree | Acceptance evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| worker-001-resource-contracts | planned | Define redacted external MCP connection details, health semantics, and engineering resource-layout persistence contract. | `src/core/studio/resource_catalog.py`, `src/core/lab/dev_flow.py`, `src/backend/main.py`, `src/backend/lite_main.py`, `scripts/tests/lite/`, backend/core tests directly covering this contract | `src/frontend/**`, `docs/planning/**`, `MENTOR_WORKERS.md`, product CSS, unrelated runtime logic | Clean baseline | `workers/worker-001-resource-contracts` | `..\CartridgeFlow-worker-001-resource-contracts` | Pending |
| worker-002-external-mcp-detail | planned | Build type-correct MCP detail templates that distinguish local source, external connection, and opaque modes. | `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, `src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx`, `src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx`, new detail-template components under the same folder, directly related frontend tests | `src/core/**`, `src/backend/**`, `FlowGraphView.tsx`, `engineeringNode.ts`, `views.tsx`, shared CSS owned by worker 003, `docs/**`, `MENTOR_WORKERS.md` | worker-001 accepted and merged into base | `workers/worker-002-external-mcp-detail` | `..\CartridgeFlow-worker-002-external-mcp-detail` | Pending |
| worker-003-engineering-canvas | planned | Render resource-specific engineering nodes, category markers, draggable canvas behavior, and adaptive card dimensions without changing APIs or detail templates. | `src/frontend/src/pages/flow-workbench/engineeringNode.ts`, `EngineeringNodeCard.tsx`, `FlowGraphView.tsx`, `FlowNodeCard.tsx`, `flowNodeView.ts`, `nodeModel.ts`, engineering-view CSS, related component/layout tests | `src/core/**`, `src/backend/**`, `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, `views.tsx`, `EngineeringInspector.tsx`, `McpTransparencyOverlay.tsx`, `docs/**`, `MENTOR_WORKERS.md` | Clean baseline; can run in parallel with worker-001 | `workers/worker-003-engineering-canvas` | `..\CartridgeFlow-worker-003-engineering-canvas` | Pending |
| worker-004-engineering-integration | planned | Connect accepted APIs, MCP detail templates, and canvas behavior; persist resource positions and produce final browser evidence. | `src/frontend/src/pages/flow-workbench/views.tsx`, `src/frontend/src/pages/FlowWorkbench.tsx` only if required for wiring, final integration/E2E tests, `docs/development/FILE_INVENTORY.md` | `src/core/**`, `src/backend/**`, `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, node-card files owned by worker-003, MCP detail components owned by worker-002, `docs/planning/**`, `MENTOR_WORKERS.md` | workers 001, 002, 003 accepted and merged into base | `workers/worker-004-engineering-integration` | `..\CartridgeFlow-worker-004-engineering-integration` | Pending |

## Worker Reports

### worker-001-resource-contracts

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-002-external-mcp-detail

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-003-engineering-canvas

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

### worker-004-engineering-integration

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: Pending
- Commit: Pending
- Tests: Pending
- Risks or follow-up: Pending
- Mentor acceptance: Pending

## Update Log

| Time | Update |
| --- | --- |
| 2026-07-30 Asia/Shanghai | Register created for `ENG-021`; three sequential, non-overlapping assignments planned. |
| 2026-07-30 Asia/Shanghai | Added `docs/development/WORKER_COLLABORATION_GUIDE.md` for the operator workflow; no worker started. |
| 2026-07-30 Asia/Shanghai | Revised delivery into two parallel initial lanes plus a dedicated final integration worker; clarified that worker 002 starts after 001 without waiting for worker 003. |
