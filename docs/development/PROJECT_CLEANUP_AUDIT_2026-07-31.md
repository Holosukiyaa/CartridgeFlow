# CartridgeFlow Full Cleanup And Chain Audit

Date: 2026-07-31

## Result

The working product boundary is now CartridgeFlow. The retired restricted-product launcher, request gate, named test group, node-coverage script name, product labels, and stale local-storage prefixes have been removed or migrated. The only retained historical storage keys are read-once migration inputs; the new keys are written immediately and the old keys are deleted.

Published protocol releases now declare their runtime adapter and semantic features in `protocol/catalog/release_manifest.json`, mirrored by each release snapshot. Runtime code asks for features such as `typed_control_edges`, `tool_transparency`, `resource_catalog_v2`, and `execution_plan`; it no longer branches on the old release numbers. Adding a future release requires a directory, a catalog entry, a snapshot, and Base adapter support, rather than edits across runner, analyzer, UI, and package code.

The current release baseline is `CF-FARP@1.0` plus `CF-CRE@1`. Both are active/supported only after evidence exists in the reference Base: execution-plan runtime, signed deterministic archive construction, Ed25519 local trust verification, trusted payload installation, activation, frontend preflight, and runtime handoff. Before that evidence gate, either release must remain draft.

## Fixed Findings

- Removed the contradictory limited API gateway. The main FastAPI application is the only launch target and all API tests use it.
- Moved the API surface tests into `scripts/tests/api` and extended the conformance runner with `api`, `lab`, and `orchestration` groups.
- Replaced retired browser-storage keys through one-time migrations in `storage.ts`.
- Added semantic adapter metadata for supported historical flow releases and explicit Base declarations for those adapters.
- Routed compatibility checks, validation, runner topology, graph projection, resource catalog selection, Portable DLC schema selection, MCP transparency gates, and release defaults through catalog features or adapters.
- Made the 0.9 protocol text self-contained. Its release relationship is retained only as release lineage; its normative sections no longer require prior text.
- Added the independent `CF-CRE@1` release-envelope contract, signature/trust implementation, production archive builder, trusted import/activation path, and frontend package status lights.
- Added a dependency-free Node.js runtime handoff demo that verifies and installs a CF-CRE archive, runs the minimum CF-FARP@1.0 execution plan, calls an OpenAI-compatible model API, and executes the declared filesystem MCP operation.
- Fixed a ReactFlow selection feedback loop that caused `Maximum update depth exceeded` during canvas initialization; browser acceptance now reports 0 errors and 0 warnings.
- Removed static UI claims about a prior protocol version. The UI displays catalog-derived current and target labels.
- Split the 3747-line reference-shell stylesheet into base, engineering, resources, and polish modules while retaining import order. Updated the style assertion to read the module set.
- Extracted HTTP request payload models from `backend/main.py` into `backend/api_models.py`; the application entry now contains assembly, helpers, and routes rather than model declarations.
- Removed 30 frontend API wrappers with no production caller. Their server routes remain public to avoid breaking external clients.
- Removed the stale planning-task parser, its three permanently failing API routes, its tests, types, and unused styles after the planning files were removed from the repository.
- Added the Creator Studio discovery-to-recipe browser smoke test; it verifies the first-layer entry stays creator-safe and enters an auditable authoring session.

## Intentional Retention

- `protocol/flow-authoring/0.1` through `1.0` remain versioned release evidence. Version strings in their documents, snapshots, migration records, and test fixtures are data, not runtime capability switches.
- The old flow-contract report builders retain their historical protocol labels because reports must identify the contract actually assessed.
- The five historical storage-key constants are compatibility migrations only. No runtime entry point, route group, test group, script, CSS class, or product name retains the retired product identity.
- Loopback URLs are intentional local-development, CORS, sandbox, and test boundaries. They are not machine-specific paths.

## Chain Map

```text
protocol/catalog/release_manifest.json
  -> ProtocolReleaseCatalog / protocol features
  -> Base adapter declaration and compatibility report
  -> manifest validation / DLC descriptor / flow analysis
  -> resource catalog / runner / graph projection
  -> FastAPI /api/base protocol catalog
  -> React workbench protocol labels and authoring behavior
```

```text
React workbench
  -> src/frontend/src/api.ts
  -> src/backend/main.py routes
  -> DevFlowManager / CartridgeRegistry / CartridgeRunner
  -> compatibility, analysis, resource, runtime, artifact services
  -> .data runtime and report artifacts
```

## Verification

- `python scripts/run_conformance.py --quiet`: passed, 329 tests; capability evidence reports 128 verified and 17 partial capabilities, with 0 failing capabilities.
- `python scripts/audit_protocol_governance.py`: passed.
- `npm run build` in `src/frontend`: passed. The host emits only the known Node 20.18/Vite minimum-version and large-entry performance notices.
- Five static UI assertions passed, including node information architecture.
- Browser acceptance on `http://127.0.0.1:5173/cartridges/dev.cf-cre-farp-acceptance/design`: CF-FARP@1.0, all six package status lights green, production `.cf-cre.zip` download completed, console 0 errors/0 warnings; screenshot is retained under `.playwright-cli` locally.
- Backend import acceptance: deleted the development source, imported the signed production archive, and received `activation.status=active`, `allowed=true`, `signature.trust_status=trusted`.
- Node handoff acceptance: `verify` passed; mock and real OpenAI-compatible HTTP runs completed with trace `start -> model_decision -> write_artifact -> complete`.
- FastAPI was imported with `TestClient`; `/api/health` returned 200 and the app registers 114 routes after removal of the three obsolete planning routes.
The build host is running Node 20.18.0 while Vite requires 20.19 or later. The build still succeeds; upgrade Node before relying on the Vite dev-server warning-free build gate. Vite also reports a large-entry performance notice; it does not affect the accepted browser flow.

## File Tree

The tree below is generated from the current non-generated workspace. It intentionally excludes `.git`, `.data`, `node_modules`, `dist`, and bytecode caches.

```text
.gitattributes
.gitignore
AGENT.md
PLAN.md
PRODUCT_EXPERIENCE_ARCHITECTURE.md
acceptance/
  model-result.txt
config/
  base/
    BASE_IMPLEMENTATION.json
    capability_evidence.json
  defaults/
    llm_retry.json
  README.md
  templates/
    llm/
      assignments.json
      providers.json
    studio/
      credentials.json
      resources.json
docs/
  development/
    FILE_INVENTORY.md
    PROJECT_CLEANUP_AUDIT_2026-07-31.md
    README.md
    skills/
      cartridgeflow-flow-author/
        agents/
          openai.yaml
        references/
          authoring-checklist.md
        scripts/
          preflight_flow.py
          simulate_authoring.ps1
        SKILL.md
      cartridgeflow-protocol-upgrader/
        agents/
          openai.yaml
        references/
          upgrade-checklist.md
        SKILL.md
protocol/
  base/
    0.1/
      specification.md
    0.2/
      release.json
      specification.md
      tool_packs.json
  catalog/
    release_manifest.json
  flow-authoring/
    0.1/
      capabilities.json
      profiles.json
      release.json
    0.2/
      capabilities.json
      profiles.json
      release.json
    0.3/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.4/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.5/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.6/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.7/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.8/
      capabilities.json
      profiles.json
      release.json
      specification.md
    0.9/
      capabilities.json
      profiles.json
      release.json
      specification.md
    1.0/
      assurance.md
      authoring-and-analysis.md
      capabilities.json
      conformance.md
      execution-plan.md
      extensions-and-lifecycle.md
      flow-and-data.md
      flow-resources.md
      governance.md
      migration.md
      overview.md
      package-and-resources.md
      profiles.json
      README.md
      release.json
      runtime-and-recovery.md
      tool-transparency.md
  governance/
    GOVERNANCE.md
    protocol_history.json
    README.md
  README.md
  release-envelope/
    1/
      capabilities.json
      profiles.json
      release.json
      specification.md
README.md
requirements.txt
run.bat
runtime-developer-toolkit/
  README.md
  guide/
    RUNTIME_TEAM_CF_CRE_FARP_DEVELOPMENT_GUIDE.md
  demo/
    mock-model.mjs
    package.json
    README.md
    run.mjs
  samples/
    dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip
    trusted_publishers.json
scripts/
  audit_protocol_governance.py
  bootstrap.ps1
  demo_cf_cre_runtime_handoff.py
  demo_personal_runtime.py
  launch.py
  run_conformance.py
  run_node_coverage.py
  tests/
    api/
      test_api_surface.py
    browser/
      test_creator_discovery.py
    conformance/
      test_base_manifest.py
      test_compatibility_report.py
      test_conformance_reporting.py
      test_mcp_source_editing_v09.py
      test_mcp_transparency_v09.py
      test_personal_runtime_demo.py
      test_protocol_adapter_dispatch.py
      test_protocol_certification.py
      test_protocol_extensions.py
      test_protocol_release_governance.py
      test_protocol_v06_contract.py
      test_protocol_v07_specification.py
      test_protocol_v08_runtime.py
      test_protocol_v08_specification.py
      test_protocol_v09_specification.py
      test_protocol_v10_completeness.py
      test_protocol_v10_execution_plan.py
      test_release_builder.py
      test_release_envelope_protocol.py
      test_resource_catalog_v08.py
      test_runtime_contract.py
    fixtures/
      portable_dlc.py
    history/
      test_protocol_history_compatibility.py
      test_protocol_v02_flow_contract.py
      test_protocol_v02_registry.py
      test_protocol_v03_flow_contract.py
      test_protocol_v03_registry.py
      test_protocol_v04_flow_contract.py
      test_protocol_v04_registry.py
    hygiene/
      test_clean_base_hygiene.py
    lab/
      test_flow_analyzer_execution_plan_projection.py
    llm/
      test_llm_config_manager.py
      test_llm_connection.py
      test_llm_detection.py
      test_llm_recipe.py
      test_llm_responses_api.py
    orchestration/
      test_execution_plan_compiler.py
    runtime/
      test_builtin_filesystem.py
      test_decision_consume.py
      test_execution_token_runner.py
      test_interaction_assets.py
      test_optional_input.py
      test_portable_dlc.py
      test_process_nodes.py
      test_runtime_decision.py
      test_runtime_errors.py
      test_runtime_interaction.py
      test_runtime_recovery.py
      test_sandboxed_interaction.py
      test_tool_plan_v1.py
      test_worker_lifecycle.py
    studio/
      test_ai_steward.py
      test_external_adapters.py
      test_flow_tool_bindings.py
      test_portability.py
      test_resource_catalog_eng021.py
      test_studio_environment.py
      test_studio_flow_directory.py
      test_studio_resources.py
    ui/
      assert_engineering_canvas.mjs
      assert_engineering_view_integration.mjs
      assert_execution_plan_projection.mjs
      assert_mcp_detail_templates.mjs
      assert_node_information_architecture.mjs
      capture_workbench.mjs
src/
  backend/
    api_models.py
    main.py
  core/
    __init__.py
    cartridge/
      __init__.py
      artifacts.py
      assets.py
      dependencies.py
      environment.py
      node_normalizer.py
      permissions.py
      registry.py
      root_flow.py
      runner.py
      validator.py
    conformance/
      __init__.py
      reporting.py
    data_paths.py
    extensions/
      __init__.py
      descriptor.py
      mcp_source_editor.py
      mcp_source_parser.py
      registry.py
      sandbox_renderer.py
      sandbox_service.py
      worker_bootstrap.py
      worker_client.py
      worker_sdk.py
    lab/
      __init__.py
      ai_steward.py
      builtin_mcp.py
      dev_flow.py
      flow_analyzer.py
      graph.py
      mcp/
        __init__.py
        shared.py
      mcp_slots.py
      node_executor.py
    llm/
      __init__.py
      base.py
      config.py
      config_manager.py
      detection.py
      errors.py
      importers.py
      openai_provider.py
      openai_responses_provider.py
      retry.py
    local_config.py
    orchestration/
      __init__.py
      execution_plan.py
    protocol/
      __init__.py
      base_manifest.py
      capability_registry.py
      certification.py
      compatibility.py
      decision_envelope.py
      features.py
      flow_contract.py
      release_builder.py
      release_catalog.py
      release_envelope.py
      release_signing.py
      report.py
      tool_plan.py
    runtime/
      __init__.py
      agent_squad.py
      checkpoints.py
      errors.py
      html_generator.py
      llm_prompt.py
      manager.py
      state_machine.py
    studio/
      __init__.py
      environment.py
      external_adapters.py
      hygiene.py
      portability.py
      release.py
      resource_catalog.py
      resource_resolver.py
      resources.py
    workspace/
      __init__.py
      host.py
  frontend/
    .gitignore
    index.html
    package.json
    package-lock.json
    public/
      favicon.svg
    README.md
    src/
      api.ts
      api.types.ts
      App.tsx
      appearance.ts
      components/
        ConfigModal.tsx
        DlcSandboxFrame.tsx
        InteractionSandboxFrame.tsx
      index.css
      llmRecipe.ts
      main.tsx
      pages/
        FlowWorkbench.tsx
        flow-workbench/
          AIFlowStewardPanel.tsx
          BrandMark.tsx
          CanvasAnnotationCard.tsx
          CartridgeDefinitionPanel.tsx
          CartridgeWorkspaceControl.tsx
          clusterLayout.ts
          EngineeringInspector.tsx
          engineeringNode.ts
          EngineeringNodeCard.tsx
          FlowGraphView.tsx
          FlowNodeCard.tsx
          FlowNodePorts.tsx
          flowNodeView.ts
          InteractionAssetEditor.tsx
          InteractionContractEditor.tsx
          McpDetailTemplates.tsx
          McpTransparencyOverlay.tsx
          newFlowSetup.ts
          nodeAuthoring.ts
          nodeBuilder.ts
          NodeExperiencePanel.tsx
          nodeExperience.ts
          NodeDetailCard.tsx
          nodeDetails.ts
          nodeEditing.ts
          nodeModel.ts
          passiveHtml.ts
          ResourceManagementPanels.tsx
          RunInputDialog.tsx
          runState.ts
          TestBench.css
          TestBenchView.tsx
          types.ts
          views.tsx
      storage.ts
      styles/
        00-foundation.css
        100-mcp-transparency.css
        10-workbench-shell.css
        15-cartridge-workspace.css
        30-workbench-runtime.css
        50-workbench-design.css
        95-config-and-appearance.css
        98-reference-theme.css
        99-workbench-reference-base.css
        99-workbench-reference-engineering.css
        99-workbench-reference-polish.css
        99-workbench-reference-resources.css
        99-workbench-reference-shell.css
        README.md
      toast.tsx
      ui.tsx
    tsconfig.app.json
    tsconfig.json
    tsconfig.node.json
    vite.config.ts
VERSION
```
