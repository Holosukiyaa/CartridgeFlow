# CartridgeFlow AI-Assisted Authoring Action Baseline

Date: 2026-08-03
Status: Frozen product and delivery baseline
Delivery ID: `creator-ai-authoring-2026-08`
Baseline revision: `creator-ai-authoring-2026-08-r1`
Frozen at: 2026-08-03 13:24 +08:00
Supersedes: the previous runtime-oriented User Experience Plan in this file

## 1. Baseline Decision

CartridgeFlow is an authoring product. Its primary user experience helps a
creator turn an unusual idea into a portable cartridge through collaboration
with AI. Production application execution belongs to the separate runtime team
and is handed off through signed cartridge packages under `demos/`.

The product is split into three surfaces:

```text
Creator Studio
  natural-language intent + creator-owned sources
  -> AI-proposed semantic design
  -> direct manipulation and explicit change acceptance
  -> progressively frozen recipes and topology
  -> validated cartridge package

Developer Console
  complete engineering and tuning information
  -> protocol facts, prompts, bindings, revisions, diffs, validation,
     materialization, diagnostics and development probes

Runtime Product
  signed cartridge install and execution
  -> owned by the runtime project team; `demos/runtime-developer-toolkit`
     is the handoff contract and reference, not a CartridgeFlow user UI
```

This document is the only active action baseline for the delivery. A Worker
must not implement the superseded ordinary-user run page or the old
`cartridgeflow.user_experience_plan.v1` direction from the prior plan.

## 2. Immediate Stop Gate

The branch `workers/worker-201-uxp-contract` contains completed commits for the
superseded runtime-oriented UXP contract. It is clean and unmerged as of this
baseline. Its tip is `d57df6a`.

- Do not merge or cherry-pick that branch into `main`.
- Preserve the worktree until the user explicitly approves cleanup.
- Do not treat its protocol versions or evidence as the next-version baseline.
- Reusable implementation details may be reconsidered only through a new,
  scope-correct Worker and must not be copied wholesale.

## 3. Product Thesis

Official business recipes cannot cover the creator's long tail of goals.
CartridgeFlow therefore does not lead with a catalog of official scenario
recipes. It leads with an AI co-author that can understand the creator's intent,
incorporate creator-selected information sources, propose a semantic flow, and
turn accepted decisions into versioned protocol artifacts.

Official supply remains necessary at a lower level:

- protocol-defined capability primitives;
- trusted source, transform, decision, review and delivery building blocks;
- type adapters and validation rules;
- permission and effect declarations;
- hidden examples and conformance fixtures used to evaluate AI authoring;
- optional starter templates, never the assumed product center.

The platform supplies the language, standard library and compiler. The creator
and AI author the specific cartridge.

## 4. Non-Negotiable Ownership Boundaries

### 4.1 Creator Studio owns

- capturing intent in ordinary language;
- adding and describing creator-owned sources;
- asking the minimum clarifying questions needed to remove ambiguity;
- presenting a semantic canvas that the creator can edit directly;
- proposing AI changes as explicit, reviewable transactions;
- progressive confirmation and freezing of steps;
- plain-language design validation;
- generating a cartridge after all blocking issues are resolved.

### 4.2 Developer Console owns

- complete Root Flow topology and contracts;
- prompts, recipe parameters and tuning revisions;
- model roles, tools, source bindings and resource preflight;
- protocol identity, digests, materialization and release provenance;
- raw validator findings and engineering diffs;
- development-only probes, traces and diagnostics;
- publishing trusted primitives and recipe blueprints.

The Developer Console is a separate frontend project connected to the same
backend through explicit APIs. It is not a hidden mode, route flag or expanding
drawer inside Creator Studio.

### 4.3 Runtime owns

- installation and trust-store enforcement;
- runtime resource and credential binding;
- production execution, pause, resume and failure routing;
- runtime interactions, queues, history, artifacts and delivery UI.

Creator Studio may perform static validation and bounded design probes. It must
not grow into a production runtime product.

## 5. Creator Mental Model

The creator sees intentions, sources, steps, decisions and deliverables. The
creator does not need to understand Prompt, schema, MCP, model role, digest,
executor, edge kind or protocol version.

Technical terminology must be translated, not used as a reason to hide
consequential behavior. Examples:

| Engineering fact | Creator wording |
| --- | --- |
| filesystem write permission | This step creates files in the delivery folder. |
| provider credential binding | This connection needs your account when the cartridge runs. |
| type mismatch | The previous step provides web addresses; this step needs a news list. |
| context limit and chunking | Long material may be processed in several sections. |
| network effect | This step sends the selected material to an external service. |

The creator must always understand external effects, required accounts,
material destinations, irreversible actions and unresolved design assumptions.

## 6. AI Co-Authoring Loop

The primary workflow is:

```text
Express intent
  -> attach or name sources
  -> answer minimal clarification
  -> inspect AI-proposed semantic steps
  -> edit by conversation or direct canvas actions
  -> review a concrete change set
  -> accept, reject or partially accept
  -> confirm and freeze stable steps
  -> resolve design findings
  -> generate the cartridge
```

AI is a protocol-aware authoring assistant, not an opaque state mutator. Every
AI proposal must produce a structured change set before it changes the accepted
design.

Required transaction lifecycle:

1. AI reads the current accepted revision and available capability catalog.
2. AI returns a proposed semantic change set plus unresolved assumptions.
3. Backend compiles the proposal into structural and recipe deltas.
4. Backend validates the proposal without changing accepted state.
5. Creator sees a plain-language summary and any consequences.
6. Creator accepts all, accepts selected changes, rejects or revises.
7. Accepted changes apply atomically with a new revision and provenance.
8. Undo creates a new reversal revision; it does not rewrite history.

Chat transcripts are supporting context, not the source of truth. Structured
accepted artifacts are the source of truth.

## 7. Progressive Solidification

Every semantic step has one authoring state:

- `exploring`: AI and creator may freely reshape the step.
- `needs_confirmation`: a concrete proposal is ready for review.
- `confirmed`: intent and visible behavior are accepted.
- `frozen`: the step has a pinned recipe blueprint, instance configuration,
  contracts and revision.
- `blocked`: required source, permission, contract or decision is unresolved.

Rules:

- A frozen step cannot change silently.
- Changing a frozen step requires explicit unlock or a proposed new revision.
- A downstream change that invalidates a frozen contract must identify the
  affected step and request a new confirmation.
- Cartridge generation fails when any step is `blocked`, any required contract
  is unresolved, or the accepted revision is stale.
- Non-blocking advice must remain distinguishable from blocking findings.

## 8. Artifact Model

The next protocol design must distinguish these artifacts:

1. **Design Intent**: creator goal, constraints and desired delivery in ordinary
   language, with a stable revision.
2. **Source Reference**: creator-selected source identity and expected role;
   never embedded credentials.
3. **Semantic Design Plan**: creator-facing steps and relations without raw
   engineering internals.
4. **Recipe Blueprint**: developer- or AI-authored reusable, versioned technical
   definition with typed contracts and declared safe controls.
5. **Recipe Instance**: a blueprint pinned into one design with a new instance
   identity and accepted creator values.
6. **Authoring Change Set**: reviewable delta with base revision, proposal
   provenance, validation and acceptance result.
7. **Freeze Snapshot**: immutable evidence tying confirmed semantics to exact
   blueprint, instance, topology and source-reference revisions.
8. **Root Flow**: CF-FARP-owned executable topology compiled from accepted
   authoring facts.
9. **Tuning Release**: immutable internal effect and recipe snapshot.
10. **Cartridge Release**: signed CF-CRE handoff package.

CF-TUNING@1.0 is host-Flow and node-ID scoped. It cannot by itself represent a
portable blueprint catalog and instantiation lifecycle. The next contract must
solve blueprint portability, instance pinning, accepted AI change provenance
and freeze semantics without moving topology ownership out of CF-FARP.

## 9. Source and Credential Rules

- A creator may add a URL, RSS feed, file role, API role, MCP capability or
  other supported source through ordinary-language UI.
- AI may infer a proposed source adapter only from declared capabilities.
- Unknown adapters remain blocked placeholders; AI must not invent executable
  tools or silently fall back to a different provider.
- Credentials, tokens and machine-local paths never enter the design artifact,
  recipe release or cartridge package.
- Runtime-specific account binding remains a runtime responsibility.
- Creator Studio must explain the required future connection in plain language.

## 10. Creator Studio Interaction Baseline

### 10.1 Default workspace

- Left: intent history, AI collaboration, creator sources and saved personal
  fragments.
- Center: semantic infinite canvas with direct manipulation.
- Right: selected step described as purpose, needs, result, adjustable behavior
  and consequences.
- Bottom: pending AI change set, design findings and solidification progress.
- Top: undo, redo, design check, save and generate cartridge.

### 10.2 Manual canvas mode

The previously explored recipe-library canvas remains useful as an advanced
manual design view. It is not the default empty-state experience.

Manual mode supports:

- drag and drop personal, trusted or generated recipe blueprints;
- connect typed ports with compatible-next-step suggestions;
- edit declared creator-safe values;
- multi-select, align, group and create personal reusable fragments;
- inspect plain-language input and output contracts;
- pin or update blueprint versions through explicit change proposals.

### 10.3 Node presentation

Creator nodes show:

- business purpose;
- solidification state;
- plain-language input and output;
- only creator-safe adjustable behavior;
- warnings and external effects;
- blueprint source and update state when relevant.

They do not show prompts, raw schemas, model/tool bindings, executors, node IDs
or protocol fields.

## 11. Developer Console Architecture

Create a separate frontend package, provisionally `src/developer-console/`.
The implementation Worker must verify the final location against repository
conventions before scaffolding.

Requirements:

- independent build, dependencies, routing and release lifecycle;
- same backend, explicit developer API namespace and privileged authorization;
- no reading development files or backend process memory from the browser;
- dense engineering canvas and inspectors optimized for complete information;
- raw/semantic side-by-side views and exact revision diffs;
- protocol validation, materialization, source binding and package preflight;
- development probes only, clearly separated from production runtime behavior;
- secrets remain references or redacted status even in the developer surface.

The two frontends may share generated API types, a small API client and basic
design tokens. They must not share page state, route assumptions or a single
conditional component tree.

## 12. Product Invariants

1. AI never mutates accepted design state without an accepted change set.
2. Every accepted change is attributable, reversible and based on an exact
   revision.
3. Frozen steps are immutable until explicitly revised.
4. Generated technical artifacts validate before cartridge generation.
5. Creator language hides jargon but not effects, permissions or uncertainty.
6. Business recipes are optional accelerators, not required product coverage.
7. Official capability primitives remain finite, trusted and protocol-defined.
8. Creator Studio and Developer Console are separate frontend applications.
9. Runtime UI and production execution remain outside Creator Studio.
10. The signed cartridge is the only production runtime handoff.

## 13. Acceptance Matrix

| Scenario | Required evidence |
| --- | --- |
| Intent to draft | A creator statement and sources produce a semantic draft with explicit assumptions and no accepted-state mutation. |
| Clarification | Missing consequential facts become a small set of answerable creator questions. |
| AI proposal | Proposal carries base revision, semantic summary, technical delta, provenance and validation result. |
| Partial acceptance | Creator can accept selected proposal items atomically and receive a new revision. |
| Direct manipulation | Canvas edits use the same change-set and revision path as conversational edits. |
| Progressive freeze | Steps transition through defined states; frozen changes require explicit revision. |
| Source safety | Source roles are portable; credentials and local paths do not enter releases. |
| Plain-language transparency | External effects, required connections and blockers remain visible without engineering jargon. |
| Blueprint instance | A portable blueprint is pinned as a distinct instance with exact version and creator-safe values. |
| Root Flow compilation | Accepted authoring facts deterministically compile into a valid CF-FARP topology. |
| Cartridge generation | Only an unblocked, current, validated design can produce a signed package. |
| Frontend separation | Creator Studio and Developer Console build independently and communicate only through declared APIs. |
| Runtime boundary | No creator UI depends on queues, production run state or runtime project internals. |

Visual appearance is not a Worker acceptance criterion. Functional semantics,
operability, protocol invariants, API behavior and automated evidence are.

## 14. Delivery Order

```text
worker-301-authoring-contract
  -> worker-302-authoring-service
     -> worker-303-creator-studio
     -> worker-304-developer-console
        -> worker-305-authoring-integration
```

Workers 303 and 304 may start in parallel only after Worker 302 is accepted and
merged. Worker 305 starts only after both frontend Workers are accepted and
merged. No Worker may cherry-pick the rejected Worker 201 branch.

## 15. Worker Cards

### Worker 301

**Name and objective:** `worker-301-authoring-contract` - publish the next
authoring contracts for portable recipe blueprints, instances, AI change sets
and progressive freezing while preserving CF-FARP topology ownership.

**Status:** `planned`

**Allowed writes:** next-version `protocol/tuning/**` and required trusted
`protocol/flow-authoring/**` release; protocol catalog/governance history;
`config/base/**`; `src/core/protocol/**`; directly related protocol,
conformance and governance tests/evidence.

**Exclusions:** backend APIs and persistence, Creator Studio, Developer Console,
runtime toolkit, dependencies, `PLAN.md`, `MENTOR_WORKERS.md`, rejected Worker
201 branch.

**Dependency and branch:** none; `workers/worker-301-authoring-contract`.

**Acceptance:** versioned immutable contracts; blueprint/instance/change-set
and freeze schemas; deterministic validation; secret redaction; exact FARP and
TUNING ownership; migration and negative tests; governance evidence passes.

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-301-authoring-contract"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-301-authoring-contract"

$prompt = @'
You are worker-301-authoring-contract. Implement the protocol foundation for
CartridgeFlow AI-assisted authoring. The active product baseline is: creators
express intent, AI proposes reviewable changes, creators progressively freeze
semantic steps, accepted facts compile to CF-FARP topology, and signed packages
are handed to a separate runtime. Do not implement an ordinary-user run page or
reuse the rejected runtime UXP branch.

Allowed writes: next-version protocol/tuning/** and required trusted
protocol/flow-authoring/** release, protocol catalog/governance history,
config/base/**, src/core/protocol/**, and directly related protocol/conformance
tests and evidence. Exclude backend APIs, persistence, both frontends, demos,
dependencies, PLAN.md and MENTOR_WORKERS.md.

Define immutable portable recipe blueprints, pinned recipe instances,
revision-based AI authoring change sets, progressive freeze snapshots, source
references without credentials, and deterministic compilation references.
CF-FARP retains topology and executable contracts. CF-TUNING owns recipe and
authoring revision facts. Reject stale revisions, silent frozen-step changes,
invented capabilities, secrets, local paths and unsafe exposed values. Preserve
all existing released protocols unchanged. Add positive and negative automated
evidence. Commit only your allowed scope.

Acceptance: new releases are versioned and trusted correctly; schemas and
validators cover every new artifact; canonical digests and redaction are
deterministic; ownership boundaries are explicit; migration is documented;
protocol/governance/conformance tests pass.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

### Worker 302

**Name and objective:** `worker-302-authoring-service` - implement authoring
sessions, AI proposal transactions, acceptance/undo, freezing and deterministic
artifact compilation behind explicit APIs.

**Status:** `planned`

**Allowed writes:** `src/backend/**`, `src/core/studio/**`, required
`src/core/cartridge/**`, `src/core/llm/**` authoring adapters, and directly
related backend/service tests.

**Exclusions:** protocol/config releases, both frontends, demos, dependency
manifests, unrelated runtime execution, mentor files.

**Dependency and branch:** accepted and merged Worker 301;
`workers/worker-302-authoring-service`.

**Acceptance:** optimistic revisions; validate-before-accept; partial
acceptance; atomic application; reversal revisions; freeze enforcement;
capability-grounded AI proposals; source/credential separation; deterministic
compile API; comprehensive API/service tests.

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-302-authoring-service"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-302-authoring-service"

$prompt = @'
You are worker-302-authoring-service. Start only from a baseline containing the
accepted worker-301 authoring contracts. Implement backend and core services for
AI-assisted creator authoring, not production application runtime.

Allowed writes: src/backend/**, src/core/studio/**, required
src/core/cartridge/** and src/core/llm/** authoring adapters, plus directly
related backend/service tests. Exclude protocol/config releases, both
frontends, demos, dependency manifests, unrelated runtime execution, PLAN.md
and MENTOR_WORKERS.md.

Implement revisioned design sessions, source references, semantic design plans,
AI proposal generation grounded only in declared capabilities, preview
validation, full and partial acceptance, atomic apply, rejection, reversal
revisions, progressive freeze enforcement, plain-language consequence data and
deterministic compilation to protocol artifacts. Chat is context, never source
of truth. Stale proposals and silent frozen-step changes fail closed. Keep
credentials and machine-local paths out of authoring artifacts. Add explicit
creator and developer API projections. Commit only your allowed scope.

Acceptance: API and service tests demonstrate no mutation before acceptance,
optimistic conflict rejection, partial acceptance, undo history, freeze guards,
source safety, deterministic compilation and stable error identities.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

### Worker 303

**Name and objective:** `worker-303-creator-studio` - turn the existing frontend
into an AI-first semantic authoring surface with direct canvas editing and
progressive solidification.

**Status:** `planned`

**Allowed writes:** `src/frontend/**` and its own frontend tests/dependency
files.

**Exclusions:** backend/core/protocol/config, new Developer Console package,
demos, mentor files.

**Dependency and branch:** accepted and merged Worker 302;
`workers/worker-303-creator-studio`.

**Acceptance:** intent/source entry; semantic canvas; proposal review with
partial acceptance; direct edits through the same transaction path; visible
solidification states; plain-language consequences; manual canvas mode;
generate-cartridge gating; frontend tests and build pass.

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-303-creator-studio"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-303-creator-studio"

$prompt = @'
You are worker-303-creator-studio. Start only after the accepted authoring
service is merged. Build the creator-facing AI co-authoring experience in the
existing frontend. It is a design product, not an application runtime.

Allowed writes: src/frontend/** and that frontend's own tests and dependency
files. Exclude backend, core, protocol, config, the separate Developer Console,
demos, PLAN.md and MENTOR_WORKERS.md.

Implement intent and source entry, semantic canvas generation, ordinary-language
step inspectors, exploring/needs-confirmation/confirmed/frozen/blocked states,
AI change-set review, partial accept/reject/revise, undo, direct canvas edits
through the same revision API, plain-language effects and blockers, design
validation and gated cartridge generation. Preserve a secondary manual canvas
for dragging generated/personal/trusted blueprints and typed connections. Hide
engineering terminology without hiding consequences. Do not add production run,
queue, runtime history or result-delivery UI. Follow established frontend
patterns and add functional automated coverage. Commit only your allowed scope.

Acceptance: a creator can express a novel goal, add sources, receive a draft,
review and partially accept changes, freeze steps, edit directly, resolve
blocking findings and generate a cartridge without seeing protocol internals;
tests and build pass.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

### Worker 304

**Name and objective:** `worker-304-developer-console` - create an independent
developer frontend for complete engineering, tuning and diagnostic visibility.

**Status:** `planned`

**Allowed writes:** new `src/developer-console/**` package and its own tests and
dependency files. The Worker may choose a different new sibling path only after
documenting why it better matches repository conventions.

**Exclusions:** existing `src/frontend/**`, backend/core/protocol/config, demos,
root dependency files, mentor files.

**Dependency and branch:** accepted and merged Worker 302;
`workers/worker-304-developer-console`.

**Acceptance:** independent build; API-only backend connection; dense full-flow
canvas; raw and semantic inspectors; prompts/bindings/revisions/diffs;
validation/materialization/preflight; redacted credentials; no Creator Studio
mode flags; tests and build pass.

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-304-developer-console"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-304-developer-console"

$prompt = @'
You are worker-304-developer-console. Start only after the accepted authoring
service is merged. Create a separate developer frontend project connected to
the same backend through declared APIs. Do not hide it inside Creator Studio.

Allowed writes: a new src/developer-console/** package with its own tests and
dependency files. You may select another new sibling package path only when you
document the repository-convention reason. Exclude src/frontend/**, backend,
core, protocol, config, demos, root dependency files, PLAN.md and
MENTOR_WORKERS.md.

Build an information-dense engineering surface for full Root Flow topology,
typed contracts, prompts, recipe parameters, model/tool/source bindings,
tuning revisions, exact diffs, protocol identity, digests, materialization,
validation, package preflight and development-only probes. Show raw and
semantic projections side by side. Connect only through explicit APIs. Never
read backend files directly. Secrets remain references or redacted status.
Keep production runtime behavior out of this console. Commit only your allowed
scope.

Acceptance: package installs/builds independently, can inspect all declared
engineering projections and diagnostics through APIs, remains isolated from
Creator Studio, does not expose credential values, and has functional tests.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

### Worker 305

**Name and objective:** `worker-305-authoring-integration` - own final
cross-surface acceptance and update only the runtime handoff documentation and
fixtures required by the new cartridge output.

**Status:** `planned`

**Allowed writes:** `demos/runtime-developer-toolkit/**`, new integration and
acceptance tests, maintained top-level/development documentation directly
describing the three-surface boundary.

**Exclusions:** product protocol/core/backend/frontend implementation,
dependencies, mentor files. Defects return to the owning Worker.

**Dependency and branch:** accepted and merged Workers 303 and 304;
`workers/worker-305-authoring-integration`.

**Acceptance:** end-to-end intent-to-package evidence; both frontends build;
package remains a standalone runtime handoff; toolkit verifies new packages
without consuming authoring state; regression suite passes; boundary docs are
accurate.

```powershell
Set-Location -LiteralPath "C:\_HOLOLAB\code\CF WS"
$worktree = "C:\_HOLOLAB\code\CF WS\CartridgeFlow-worker-305-authoring-integration"
git -C ".\CartridgeFlow" worktree add $worktree -b "workers/worker-305-authoring-integration"

$prompt = @'
You are worker-305-authoring-integration. Start only after accepted Creator
Studio and Developer Console work is merged. Own final cross-surface evidence
and the minimal runtime handoff update. Do not implement product defects in
files owned by other Workers; report them to the owner.

Allowed writes: demos/runtime-developer-toolkit/**, new integration/acceptance
tests, and maintained top-level/development documentation directly describing
the three-surface boundary. Exclude protocol, config, core, backend, both
frontend implementations, dependencies, PLAN.md and MENTOR_WORKERS.md.

Prove the complete path from creator intent and accepted AI change sets through
progressive freezing, deterministic Root Flow compilation and signed cartridge
generation. Verify both frontends build independently. Update the runtime
toolkit only where the public cartridge handoff changed; it must not consume
chat, design sessions, developer repositories or frontend state. Run broad
regression evidence and commit only your allowed scope.

Acceptance: standalone toolkit verifies generated packages; authoring-private
state is absent from runtime inputs; creator and developer surfaces build;
integration and regression tests pass; documentation states the ownership
boundary unambiguously.

## Worker Delivery Report
Changed files: <one path per line>
Commit SHA: <full SHA>
Tests: <command and result per line>
Known risks: <none or concrete risks>
Scope confirmation: <confirm no excluded paths changed>
'@
codex -C $worktree $prompt
```

## 16. Visual Design Milestones

Visual exploration proceeds before Worker 303 implementation acceptance:

1. AI co-authoring workspace during an active design conversation.
2. AI proposal review with partial acceptance and consequences.
3. Progressive freeze and blocked-source states on the semantic canvas.
4. Advanced manual canvas using generated and personal blueprints.
5. Separate information-dense Developer Console.

The next image is milestone 1. It must show a novel creator request, three
creator-selected sources, five AI-proposed semantic steps, mixed solidification
states, one unresolved source, and a pending reviewable change set. It must not
show application runtime, queue, media results or raw engineering terminology.
