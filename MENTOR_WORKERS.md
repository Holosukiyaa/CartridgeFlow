# Mentor Worker Register

Project: CartridgeFlow
Repository root: `C:\_HOLOLAB\code\CF WS\CartridgeFlow`
Last updated: 2026-07-30 Asia/Shanghai
Mentor: Codex mentor-orchestrator

## Current Delivery Plan: ORCH-001

Baseline: `9e7124a` (`docs: define orchestration delivery roadmap`). Delivery source: [n8n 编排取经与差异化报告](docs/architecture/N8N_ORCHESTRATION_BENCHMARK_REPORT.md). The goal is not n8n compatibility: it is one explicit, independently implemented `ExecutionPlan` semantic contract shared by protocol validation, Analyzer, runner, and engineering view.

1. `worker-101-execution-plan-contract` is merged as `213385e`. It owns protocol facts, release registry, capability vocabulary, and contract validation; `CF-FARP@1.0` remains draft/unsupported until the runner exists.
2. `worker-102-execution-plan-compiler` is merged as `2adc446`. It creates the pure compiled-plan model and owns the shared `src/core/orchestration/` package.
3. worker 103 is merged as `cafa32c`: token execution is implemented but `CF-FARP@1.0` remains draft/unsupported until the protocol owner promotes Base support. Worker 104 is merged and repaired as `2e0d0ba` plus the ORCH-001 closure commit: Analyzer keeps compiled-plan projection separate from Base run/package/publish gates.
4. Fixture/TestBench, typed ports, sub Flow, product delivery and adapter work deliberately remain out of this delivery. ORCH-001 is closed with a clean conformance baseline.

Known boundary: `CF-FARP@1.0` remains protocol-governance draft/unsupported. A future protocol promotion must add Base support and evidence before the Analyzer can open v1.0 run/package/publish gates.

No worker may merge another worker branch. The mentor automatically merges an accepted worker when scope, independent evidence, and integration checks pass; it pauses only for a concrete conflict, failed evidence, or material unresolved risk. Full task cards and paste-safe commands live in [ORCHESTRATION_EXECUTION_TASK_BRIEF.md](docs/planning/ORCHESTRATION_EXECUTION_TASK_BRIEF.md).

## Current Workers

| Worker | Status | Objective | Allowed write paths | Exclusions | Dependencies | Branch | Worktree | Acceptance evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| worker-101-execution-plan-contract | accepted | Freeze CF-FARP@1.0 ExecutionPlan semantics and reject ambiguous or non-executable Flow facts. | `docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md`, `docs/protocol/governance/GOVERNANCE.md`, `protocol/releases/CF-FARP-1.0.json`, `protocol/catalog/release_manifest.json`, `protocol/governance/protocol_history.json`, `protocol/vocabulary/*`, `src/core/protocol/flow_contract.py`, directly related conformance tests | `config/base/BASE_IMPLEMENTATION.json`, `src/core/cartridge/**`, `src/core/lab/**`, `src/core/runtime/**`, `src/frontend/**`, `src/backend/**`, `MENTOR_WORKERS.md` | Baseline `9e7124a` | `workers/worker-101-execution-plan-contract` | `..\CartridgeFlow-worker-101-execution-plan-contract` | Accepted and automatically merged into `main` as `213385e`; v1.0 is registry-recognized draft/unsupported, v0.9 remains current, and Base does not claim v1.0 support. |
| worker-102-execution-plan-compiler | accepted | Compile validated v1.0 Flow facts into deterministic, serializable ExecutionPlan v1 without running nodes. | new `src/core/orchestration/**`, directly related `scripts/tests/orchestration/**` | `src/core/protocol/**`, `protocol/**`, `config/**`, `src/core/cartridge/**`, `src/core/lab/**`, `src/core/runtime/**`, `src/frontend/**`, `src/backend/**`, `MENTOR_WORKERS.md` | worker 101 merged as `213385e` | `workers/worker-102-execution-plan-compiler` | `..\CartridgeFlow-worker-102-execution-plan-compiler` | Accepted and automatically merged into `main` as `2adc446`; deterministic pure compilation and stable invalid-contract errors are covered by tests. |
| worker-103-token-runner | accepted | Make the runner consume ExecutionPlan tokens, checkpoints and replay boundaries instead of global `visited` scheduling. | `src/core/cartridge/root_flow.py`, `src/core/cartridge/runner.py`, `src/core/runtime/checkpoints.py`, directly related `scripts/tests/runtime/**` | `src/core/orchestration/**`, `src/core/protocol/**`, `protocol/**`, `src/core/lab/**`, `src/frontend/**`, `src/backend/**`, `MENTOR_WORKERS.md` | worker 102 merged as `2adc446` | `workers/worker-103-token-runner` | `..\CartridgeFlow-worker-103-token-runner` | Accepted and automatically merged into `main` as `cafa32c`; loop/fork/join/wait token traces and side-effect replay confirmation are covered by runtime tests. |
| worker-104-plan-projection | accepted | Project ExecutionPlan semantics into Analyzer and engineering view; visual executable edges must agree with the plan. | `src/core/lab/flow_analyzer.py`, `src/frontend/src/pages/flow-workbench/**`, directly related analyzer/UI tests | `src/core/orchestration/**`, `src/core/protocol/**`, `protocol/**`, `src/core/cartridge/**`, `src/core/runtime/**`, `src/backend/**`, `MENTOR_WORKERS.md` | worker 102 merged as `2adc446`; repaired on main | `workers/worker-104-plan-projection` | `..\CartridgeFlow-worker-104-plan-projection` | Accepted and merged as `2e0d0ba`, then corrected in the ORCH-001 closure commit: compiler success retains plan-edge projection but cannot open run/package/publish gates until Base declares CF-FARP@1.0 support. |

## Completed ENG-021 Workers

| Worker | Status | Objective | Allowed write paths | Exclusions | Dependencies | Branch | Worktree | Acceptance evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| worker-001-resource-contracts | accepted | Define redacted external MCP connection details, health semantics, and engineering resource-layout persistence contract. | `src/core/studio/resource_catalog.py`, `src/core/lab/dev_flow.py`, `src/backend/main.py`, `src/backend/lite_main.py`, `scripts/tests/lite/`, backend/core tests directly covering this contract | `src/frontend/**`, `docs/planning/**`, `MENTOR_WORKERS.md`, product CSS, unrelated runtime logic | Clean baseline | `workers/worker-001-resource-contracts` | `..\CartridgeFlow-worker-001-resource-contracts` | Accepted and merged into `main` as `8194f73`; redaction and real probe tests passed. |
| worker-002-external-mcp-detail | accepted | Build type-correct MCP detail templates that distinguish local source, external connection, and opaque modes. | `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, `src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx`, `src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx`, new detail-template components under the same folder, directly related frontend tests | `src/core/**`, `src/backend/**`, `FlowGraphView.tsx`, `engineeringNode.ts`, `views.tsx`, shared CSS owned by worker 003, `docs/**`, `MENTOR_WORKERS.md` | worker-001 accepted and merged into base | `workers/worker-002-external-mcp-detail` | `..\CartridgeFlow-worker-002-external-mcp-detail` | Accepted and merged into `main` as `979d870`; UI assertions and production build passed. |
| worker-003-engineering-canvas | accepted | Render resource-specific engineering nodes, category markers, draggable canvas behavior, and adaptive card dimensions without changing APIs or detail templates. | `src/frontend/src/pages/flow-workbench/engineeringNode.ts`, `EngineeringNodeCard.tsx`, `FlowGraphView.tsx`, `FlowNodeCard.tsx`, `nodeModel.ts`, engineering-view CSS, related component/layout tests | `src/core/**`, `src/backend/**`, `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, `views.tsx`, `EngineeringInspector.tsx`, `McpTransparencyOverlay.tsx`, `docs/**`, `MENTOR_WORKERS.md` | Clean baseline; can run in parallel with worker-001 | `workers/worker-003-engineering-canvas` | `..\CartridgeFlow-worker-003-engineering-canvas` | Accepted and merged into `main` as `786bbde`; build and engineering assertions passed. |
| worker-004-engineering-integration | accepted | Connect accepted APIs, MCP detail templates, and canvas behavior; persist resource positions and produce final browser evidence. | `src/frontend/src/pages/flow-workbench/views.tsx`, `src/frontend/src/pages/FlowWorkbench.tsx` only if required for wiring, final integration/E2E tests, `docs/development/FILE_INVENTORY.md` | `src/core/**`, `src/backend/**`, `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, node-card files owned by worker-003, MCP detail components owned by worker-002, `docs/planning/**`, `MENTOR_WORKERS.md` | workers 001, 002, 003 accepted and merged into base | `workers/worker-004-engineering-integration` | `..\CartridgeFlow-worker-004-engineering-integration` | Accepted and integrated into `main` as `d3d9bd0`; UI/build evidence passed. Project conformance remains blocked by stale TODO hygiene assertion. |

## Worker Reports

### worker-101-execution-plan-contract

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `docs/protocol/flow-authoring/CARTRIDGEFLOW_FLOW_AUTHORING_RUNTIME_PROTOCOL_v1.0.md`, `docs/protocol/governance/GOVERNANCE.md`, `protocol/catalog/release_manifest.json`, `protocol/governance/protocol_history.json`, `protocol/releases/CF-FARP-1.0.json`, `protocol/vocabulary/capabilities-1.0.json`, `protocol/vocabulary/profiles-1.0.json`, `scripts/tests/conformance/test_protocol_v10_execution_plan.py`, `src/core/protocol/flow_contract.py`
- Commit: `1ecc77c37665eaa4d96cdca04c6e7e746e126e61` (`docs: freeze CF-FARP 1.0 execution plan contract`)
- Tests: worker reported v1.0 conformance (12 passed), protocol governance audit, and 298/299 full-conformance results with only the known TODO-status failure. Mentor independently ran v1.0 conformance (12 passed), `python scripts/audit_protocol_governance.py`, v0.9 specification conformance (5 passed), v0.4/v0.3/v0.2 history compatibility (4 passed), and `git diff --check`; all passed.
- Risks or follow-up: `CF-FARP@1.0` intentionally remains draft/unsupported. It has no runner, runtime compatibility dispatch, checkpoint implementation, or certification claim. Full conformance still has the known stale TODO-status assertion. `autoreview` could not run because TruffleHog is unavailable.
- Mentor acceptance: Accepted on 2026-07-30. The commit descends from `9e7124a`, touches only its allowed scope, preserves v0.9 and the Base support matrix, and establishes explicit positive/negative contract evidence for all ORCH-001 relation kinds. It was automatically merged into `main` as `213385e`; worker 102 may start.

### worker-102-execution-plan-compiler

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `src/core/orchestration/__init__.py`, `src/core/orchestration/execution_plan.py`, `scripts/tests/orchestration/test_execution_plan_compiler.py`
- Commit: `fd03bd790325affcbdd497f134890c14498775bf` (`feat: add execution plan compiler`)
- Tests: worker reported compiler tests (5 passed) and v1.0 protocol conformance (12 passed). Mentor independently reran both, plus `python scripts/audit_protocol_governance.py` and `git diff --check`; all passed.
- Risks or follow-up: The compiler intentionally does not execute a plan, resolve runtime values, write checkpoints, or provide runtime compatibility dispatch. `autoreview` could not run because TruffleHog is unavailable.
- Mentor acceptance: Accepted and automatically merged on 2026-07-30 as `2adc446`. The commit descends from `213385e`, writes only its owned new package/tests, produces deterministic digest-bound plans, and proves no node execution or I/O during compilation. Workers 103 and 104 are dependency-ready but must wait for a clean root baseline.

### worker-104-plan-projection

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `scripts/tests/lab/test_flow_analyzer_execution_plan_projection.py`, `scripts/tests/ui/assert_execution_plan_projection.mjs`, `src/core/lab/flow_analyzer.py`, `src/frontend/src/pages/flow-workbench/FlowGraphView.tsx`, `src/frontend/src/pages/flow-workbench/engineeringNode.ts`, `src/frontend/src/pages/flow-workbench/views.tsx`
- Commit: `3fb7ced0407eb8e491387c9cdd292e971a3fd773` (`feat: project execution plans in analyzer and canvas`)
- Tests: worker reported Analyzer/UI/build checks. Mentor independently reran its targeted Analyzer suite (2 tests passed), UI assertion, production frontend build, and whitespace validation; these passed. The build retains the existing Node `20.18.0`/Vite version warning and large-bundle warning.
- Known risks: `autoreview` could not run because TruffleHog is unavailable.
- Mentor acceptance: Accepted on 2026-07-30 after direct repair. The projection commit was merged as `2e0d0ba`; its closure patch adds the `v10_base_runtime_unsupported` blocker, `execution_plan.runtime_status`, and a regression proving that a compiled v1.0 plan stays non-runnable, non-packagable and non-publishable without a matching Base declaration. The plan-edge engineering projection remains available, and the UI labels it as engineering-only while unsupported.

### worker-103-token-runner

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `src/core/cartridge/root_flow.py`, `src/core/cartridge/runner.py`, `src/core/runtime/checkpoints.py`, `scripts/tests/runtime/test_execution_token_runner.py`
- Commit: `0b1c52f8bc2d73d3650218f87a399581f7293bb6` (`feat: run execution plans with durable tokens`)
- Tests: worker reported runtime discovery (99 passed), compiler/v1.0 protocol tests (17 passed), and compileall. Mentor independently reran the same three checks plus diff whitespace validation; all passed.
- Risks or follow-up: CF-FARP@1.0 is correctly rejected by `create_run` compatibility before compilation or Token execution because Base still declares it unsupported. Protocol promotion, compatibility dispatch and certification are outside this worker's paths. `autoreview` could not run because TruffleHog is unavailable.
- Mentor acceptance: Accepted and automatically merged on 2026-07-30 as `cafa32c`. The commit descends from `2adc446`, remains within its owned paths, records durable token identity/checkpoints, and proves that unsafe side-effect recovery requires explicit confirmation without replay.

### worker-001-resource-contracts

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `src/core/studio/resource_catalog.py`, `src/backend/main.py`, `scripts/tests/studio/test_resource_catalog_eng021.py`, `scripts/tests/lite/test_lite_api_surface.py`
- Commit: `a2d28ea7204d28cb1bff0d3c0a9c481c3c47229e` (`feat: add engineering resource connector contracts`)
- Tests: worker reported `python scripts/run_conformance.py` (287 passed), targeted resource/Lite/catalog tests (22 passed), `compileall`, and `git diff --check`; mentor independently reran `PYTHONPATH=src python -m unittest scripts.tests.studio.test_resource_catalog_eng021 scripts.tests.lite.test_lite_api_surface` (18 passed) and patch whitespace validation.
- Risks or follow-up: Connection health is process-local and run telemetry remains `not_observed`; HTTP probing uses a non-invasive `HEAD`, so services that do not support it report their genuine probe failure. `autoreview` did not run because TruffleHog is absent.
- Mentor acceptance: Accepted on 2026-07-30. The commit is scoped, based on `e4d95d3`, exposes redacted detail and stable connectivity errors, and does not manufacture a successful probe. User-approved cherry-pick completed on `main` as `8194f73`.

### worker-002-external-mcp-detail

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `src/frontend/src/api.ts`, `src/frontend/src/api.types.ts`, `src/frontend/src/pages/flow-workbench/EngineeringInspector.tsx`, `src/frontend/src/pages/flow-workbench/McpTransparencyOverlay.tsx`, `src/frontend/src/pages/flow-workbench/McpDetailTemplates.tsx`, `scripts/tests/ui/assert_mcp_detail_templates.mjs`
- Commit: `30aef40624ba35bf493d361c7736e76f34dead25` (`feat: add external MCP detail templates`)
- Tests: worker reported MCP-template and engineering-canvas assertions, production build, and whitespace check. Mentor independently reran `node scripts/tests/ui/assert_mcp_detail_templates.mjs`, `node scripts/tests/ui/assert_engineering_canvas.mjs`, and `npm run build`; all passed. `git diff --check` passed.
- Risks or follow-up: Runtime track remains `not_observed` until backend publishes public telemetry. Vite warns that Node `20.18.0` is below its preferred `20.19+` and the production bundle exceeds 500 kB. `autoreview` did not run because TruffleHog is absent. The report used the legacy four-field format because this worker began before the new embedded report template; later workers must include scope confirmation.
- Mentor acceptance: Accepted on 2026-07-30. The commit consumes the worker-001 resource contracts, keeps source editing only in the local-parsable branch, and routes external/unauditable MCPs to Chinese connection/known-contract templates. User-approved cherry-pick completed on `main` as `979d870`.

### worker-003-engineering-canvas

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `src/frontend/src/pages/flow-workbench/engineeringNode.ts`, `EngineeringNodeCard.tsx`, `FlowGraphView.tsx`, `FlowNodeCard.tsx`, `nodeModel.ts`, `src/frontend/src/styles/99-workbench-reference-shell.css`, `scripts/tests/ui/assert_engineering_canvas.mjs`
- Commit: `6fa5a0b03f44d212279da3f12b0d4d94d9be9d68` (`feat(canvas): add engineering resource cards`)
- Tests: worker reported Playwright validation for resource cards, dependency edges and resource drag; mentor independently reran `node scripts/tests/ui/assert_engineering_canvas.mjs` and `npm run build`, both passed. `git diff --check` passed.
- Risks or follow-up: Resource positions are session-local until worker-004 owns persistence; an existing React maximum update-depth console error remains outside this commit's scope. `autoreview` did not run because TruffleHog is absent. Build also warns that the installed Node `20.18.0` is below Vite's stated `20.19+` requirement and that the production chunk exceeds 500 kB.
- Mentor acceptance: Accepted on 2026-07-30. Resource nodes remain engineering-only: they are excluded from persisted business layout and Root Flow control edges, while category markers and content-dependent dimensions are covered by the assertions. User-approved cherry-pick completed on `main` as `786bbde`.

### worker-004-engineering-integration

- Prompt issued: 2026-07-30 Asia/Shanghai
- Changed files: `docs/development/FILE_INVENTORY.md`, `scripts/tests/ui/assert_engineering_view_integration.mjs`, `src/frontend/src/pages/FlowWorkbench.tsx`, `src/frontend/src/pages/flow-workbench/views.tsx`
- Commit: `e19e4312094ccd99e0e57e45d89d5615195c3d8f` (`feat(workbench): persist engineering resource layout`)
- Tests: worker reported Playwright validation across the three MCP modes, drag persistence and desktop/narrow viewports; mentor independently reran engineering integration, canvas and MCP-detail assertions plus `npm run build`, all passed. `git diff --check` passed.
- Risks or follow-up: AI 日报卡仍需要本机绑定两个外部 MCP 才能通过资源预检. Existing React maximum update-depth console errors remain observed. Vite warns that Node `20.18.0` is below its preferred `20.19+` and the bundle exceeds 500 kB. The worker worktree contains untracked `.playwright-cli/` and `output/` artifacts, so it is not yet eligible for cleanup. Full conformance is currently blocked by the stale `test_project_planning_docs_stay_focused` assertion, which rejects completed TODO entries (`5 != 1`); this pre-existed the worker commit and lies outside its allowed paths.
- Mentor acceptance: Accepted on 2026-07-30. The commit is scoped and based on `d87c7ec`; it persists only engineering-resource positions in local storage, filters resource nodes from business layout writes, and correctly routes MCP resource cards without exposing external source. User-approved integration completed on `main` as `d3d9bd0`; full delivery closure remains blocked until the TODO hygiene test is corrected and conformance passes.

## Update Log

| Time | Update |
| --- | --- |
| 2026-07-30 Asia/Shanghai | Register created for `ENG-021`; three sequential, non-overlapping assignments planned. |
| 2026-07-30 Asia/Shanghai | Added `docs/development/WORKER_COLLABORATION_GUIDE.md` for the operator workflow; no worker started. |
| 2026-07-30 Asia/Shanghai | Revised delivery into two parallel initial lanes plus a dedicated final integration worker; clarified that worker 002 starts after 001 without waiting for worker 003. |
| 2026-07-30 Asia/Shanghai | Accepted worker-001 commit `a2d28ea`; it remains unmerged pending explicit user approval. |
| 2026-07-30 Asia/Shanghai | User approved merge; cherry-picked worker-001 into `main` as `8194f73` without conflicts. |
| 2026-07-30 Asia/Shanghai | Accepted worker-003 commit `6fa5a0b`; it remains unmerged pending explicit user approval. |
| 2026-07-30 Asia/Shanghai | User approved merge; cherry-picked worker-003 into `main` as `786bbde` without conflicts. |
| 2026-07-30 Asia/Shanghai | Upgraded collaboration guidance: worker prompts now carry their own scope and fixed report contract; all completion worktrees are cleaned only after accepted merge and final delivery verification. |
| 2026-07-30 Asia/Shanghai | Accepted worker-002 commit `30aef406`; it remains unmerged pending explicit user approval. |
| 2026-07-30 Asia/Shanghai | User approved merge; cherry-picked worker-002 into `main` as `979d870` without conflicts. |
| 2026-07-30 Asia/Shanghai | Accepted worker-004 commit `e19e431`; it remains unmerged pending explicit user approval. Full conformance is blocked by a pre-existing TODO hygiene assertion. |
| 2026-07-30 Asia/Shanghai | User approved worker-004 integration. Its source and UI-test changes were applied to `main` as `d3d9bd0`; `FILE_INVENTORY.md` remains alongside the user's uncommitted documentation edits. |
| 2026-07-30 Asia/Shanghai | Created the `ORCH-001` delivery register from the n8n orchestration benchmark. Current baseline is `9e7124a`; worker 101 is the sole launchable protocol-contract worker, followed by 102, then parallel 103/104. |
| 2026-07-30 Asia/Shanghai | Accepted worker-101 commit `1ecc77c`; it remains unmerged pending explicit user approval. Independent v1.0, v0.9/history, governance, scope, and whitespace checks passed. |
| 2026-07-30 Asia/Shanghai | User authorized automatic merging after mentor acceptance. Worker-101 was merged without conflict as `213385e`; worker 102 is now launchable. |
| 2026-07-30 Asia/Shanghai | Accepted and automatically merged worker-102 as `2adc446`; compiler, v1.0 contract, governance, scope, and whitespace checks passed. Root worktree contains separate user documentation changes, so workers 103/104 await a clean baseline. |
| 2026-07-30 Asia/Shanghai | Rejected worker-104 commit `3fb7ced`: its Analyzer presents a draft/unsupported v1.0 plan as runnable and publishable. Targeted tests/build pass but do not cover the unsupported-runtime gate; a scoped fix is required before merge. |
| 2026-07-30 Asia/Shanghai | Accepted and automatically merged worker-103 as `cafa32c`; 99 runtime tests plus compiler/protocol, compile and scope checks passed. Compatibility continues to block CF-FARP@1.0 before the new token executor until protocol promotion. |
| 2026-07-30 Asia/Shanghai | Removed the clean, integrated worktrees for workers 001, 002, 003, 101, 102 and 103. Their local branches remain because the accepted changes were cherry-picked and Git correctly rejects non-forced branch deletion. Worker 004 remains dirty; worker 104 remains rejected and unmerged. |
| 2026-07-30 Asia/Shanghai | Closed ORCH-001: worker-104 projection merged as `2e0d0ba` and directly repaired so a compiled draft plan cannot open run/package/publish gates without Base support. Targeted Analyzer/UI/build/v1.0 conformance and full conformance (313) passed. Worker-004 test artifacts and both remaining worker worktrees were removed after verification. |
