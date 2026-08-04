export interface RuntimeErrorEnvelope {
  schema: 'runtime_error_envelope.v1' | string
  error_id: string
  code: string
  category: string
  message: string
  run_id: string
  node_id: string
  source: string
  missing_inputs: string[]
  retryable: boolean
  recoverable: boolean
  recovery_actions: string[]
  cause_chain: Array<{ type: string; message: string }>
  context?: Record<string, any>
  created_at?: string
}

export interface CartridgeSummary {
  id: string
  name: string
  version: string
  kind?: string
  category?: string
  description?: string
  publisher?: any
  branding?: any
  runtime?: { type?: string; adapter?: string; config?: any }
  base_contract?: any
  runtime_contract?: any
  delivery_readiness?: any
  protocol_certification?: any
  workspace?: any
  inputs?: CartridgeInput[]
  outputs?: any[]
  mcp_tools?: McpTool[]
  resource_requirements?: ResourceRequirement[]
  llm_recipe?: any
  portable_dlc?: any
  source?: string
  editable?: boolean
}

export interface ResourceRequirement {
  role: string
  kinds: string[]
  required?: boolean
  capabilities?: string[]
  constraints?: Record<string, any>
}

export interface CartridgeInput {
  id: string
  label?: string
  type: 'text' | 'textarea' | 'select' | string
  required?: boolean
  default?: string
  placeholder?: string
  options?: { value: string; label: string }[]
}

export interface CartridgeDetail extends CartridgeSummary {
  manifest?: any
  root_flow?: any
  package_path?: string
  welcome_content?: string
  welcome_html_content?: string
}

export interface RunResult {
  run_id: string
  cartridge_id: string
  cartridge_version?: string
  status: string
  current_state: string
  inputs?: Record<string, any>
  test_mode?: Record<string, any>
  run_mode?: string
  probe_range?: TestProbeRange & { node_count?: number }
  artifacts?: ArtifactItem[]
  delivery?: {
    summary?: string
    artifacts?: ArtifactItem[]
    actions?: { label: string; url: string }[]
  }
  created_at?: string
  updated_at?: string
  data_chain?: DataChainReport
  pending_interaction?: any
  base?: any
  protocol?: any
  compatibility?: CompatibilityReport
  error?: RuntimeErrorEnvelope
  errors?: RuntimeErrorEnvelope[]
}

export interface DataChainBreak {
  node: string
  title?: string
  key: string
  detail?: string
  seeded_by_probe?: boolean
}

export interface DataChainReport {
  passed: boolean
  summary?: string
  breaks: DataChainBreak[]
  probe_seeded?: string[] | null
}

export interface ArtifactItem {
  artifact_id?: string
  name: string
  type: string
  url: string
  path?: string
  display_path?: string
  mime_type?: string
  source?: any
}

// ── Flow 实验室相关类型 ──────────────────────────────────────────────
export interface FlowGraph {
  id?: string
  name?: string
  mode?: string
  cartridge_id?: string
  nodes: FlowNode[]
  edges: FlowEdge[]
  annotations?: FlowAnnotation[]
  sub_flows?: any[]
  analysis?: FlowAnalysisReport
  engineering_relations?: FlowEngineeringRelation[]
}

export interface CreatorFieldContract {
  id: string
  label: string
  value_type: 'string' | 'string_list' | 'boolean' | 'number'
  required: boolean
  default: unknown
}

export interface CreatorTrustedRecipeNode {
  id: string
  label: string
  preset: { id: string; revision: number; digest: string }
  values: Record<string, unknown>
  editable_fields: CreatorFieldContract[]
}

export interface CreatorProposal {
  proposal_id: string
  revision: number
  summary: string
  changes: Array<{ id: string; target_id: string; operation: string }>
}

export interface CreatorFinding {
  code: string
  severity: string
  message: string
  step_id?: string
}

export interface CreatorProjection {
  project_id: string
  session_id: string
  revision: number
  intent: string
  trusted_recipe: {
    id: string
    goal: string
    nodes: CreatorTrustedRecipeNode[]
    relations: Array<{ id: string; from_node_id: string; to_node_id: string; relation: string }>
  }
  frozen_steps: string[]
  pending_proposals: CreatorProposal[]
  history: Array<{ id: string; revision: number; summary: string }>
  blocked_findings: CreatorFinding[]
  generation_readiness: { ready: boolean; blocked_findings: CreatorFinding[] }
}

export interface CreatorCapabilityGap {
  schema: string
  goal: string
  needed_capabilities: string[]
  available_preset_ids: string[]
}

export interface CreatorProposalPreview {
  accepted_change_ids: string[]
  impact: { plain_summary?: string; changed_steps?: string[]; changed_sources?: string[] }
}

export interface FlowAnalysisFinding {
  id?: string
  severity: 'blocker' | 'warning' | 'info' | string
  code: string
  message: string
  node_id?: string
  path?: string
  stage?: string
}

export interface FlowAnalysisReport {
  schema?: string
  target?: string
  source_digest?: string
  findings?: FlowAnalysisFinding[]
  summary?: {
    blockers?: number
    warnings?: number
    infos?: number
    runnable?: boolean
    packagable?: boolean
    publishable?: boolean
  }
}

export interface AuthoringReadinessItem {
  id: string
  area: 'flow' | 'inputs' | 'models' | 'tools' | 'delivery' | string
  severity: 'blocker' | 'warning' | string
  code: string
  message: string
  node_id?: string
  action?: { type: 'node' | 'panel' | string; target: string; label: string }
}

export interface AuthoringReadiness {
  schema: string
  status: 'blocked' | 'warning' | 'ready'
  can_run: boolean
  source_digest?: string
  summary: { blockers: number; warnings: number }
  items: AuthoringReadinessItem[]
}

export interface FlowEngineeringEndpoint {
  type: string
  node_id?: string
  id?: string
  port?: string
}

export interface FlowEngineeringRelation {
  id: string
  kind: 'control' | 'data' | 'tool_dependency' | 'model_dependency' | 'mcp_dependency' | 'component_dependency' | string
  from: FlowEngineeringEndpoint
  to: FlowEngineeringEndpoint
  derived_from?: string[]
  confidence?: string
  runtime_effect?: boolean
  executable?: boolean
  plan_edge_id?: string
  plan_edge_kind?: string
}

export interface FlowAnnotation {
  id: string
  title: string
  body: string
  x: number
  y: number
  width: number
  height: number
  tone: 'neutral' | 'warning'
  collapsed?: boolean
  anchor?: { type: 'node'; id: string }
}

export type NodeExperienceInteractionMode = 'automatic' | 'input' | 'review' | 'choice'
export type NodeExperienceMaterialVisibility = 'none' | 'output' | 'input_output'
export type NodeExperienceControlType = 'text' | 'number' | 'slider' | 'select' | 'toggle'
export type NodeExperienceInputControlType = 'text' | 'textarea' | 'number' | 'date' | 'select' | 'toggle'

export interface NodeExperienceInputField {
  field: string
  label: string
  help: string
  placeholder: string
  control: NodeExperienceInputControlType
  required: boolean
  options: string[]
}

export interface NodeExperienceControl {
  parameter: string
  label: string
  help: string
  control: NodeExperienceControlType
  required: boolean
  options: string[]
  minimum: number | null
  maximum: number | null
  step: number | null
}

export interface NodeExperience {
  schema: 'cartridgeflow.node_experience.v1'
  visible: boolean
  stage: {
    label: string
    description: string
    waiting: string
    running: string
    success: string
  }
  interaction: {
    mode: NodeExperienceInteractionMode
    prompt: string
    action_labels: Record<string, string>
    fields: NodeExperienceInputField[]
    allow_retry: boolean
    allow_cancel: boolean
  }
  materials: {
    visibility: NodeExperienceMaterialVisibility
    label: string
    live_updates: boolean
    allow_download: boolean
    hidden_fields: string[]
  }
  outcome: {
    success_title: string
    result_label: string
    empty_text: string
    error_title: string
    error_message: string
    retry_label: string
    preserve_partial: boolean
  }
  controls: NodeExperienceControl[]
}

export interface FlowNode {
  id: string
  title: string
  type: string
  action?: string
  next?: string
  kind?: string
  executor?: string
  effect?: string
  display_name?: string
  description?: string
  experience?: NodeExperience
  component_ref?: string
  interaction_mode?: 'display' | 'collect' | 'review' | string
  input_binding?: Record<string, string>
  inputs?: Record<string, any>
  outputs?: Record<string, any>
  action_routes?: Record<string, string>
  output?: string
  display?: { label?: string; suffix?: string; [key: string]: any }
  input_kind?: string
  source?: string
  input_schema?: any
  output_contract?: string
  decision_contract?: any
  decision_test_mode?: string
  mock_decision_envelope?: any
  primary_output?: string
  tool_binding?: string
  allowed_tools?: string[]
  mcp_binding?: any
  failure_policy?: string
  permission?: string
  audit_log?: boolean
  endpoint?: string
  timeout_ms?: number
  x: number
  y: number
  scope?: string
  locked?: boolean
  entry_kind?: string
  template_id?: string
  agent?: string
  tools?: any[]
  tool_summary?: { mcp?: string; builtin?: string }
  params?: Record<string, any>
  model_role?: string
  data?: any
}

export interface FlowEdge {
  from: string
  to: string
  scope?: string
  label?: string
  kind?: string
}

export interface FlowLabItem extends CartridgeSummary {
  flow_kind?: string
}

export interface FlowLabDetail {
  cartridge: CartridgeDetail
  graph: FlowGraph
  runs: RunResult[]
  latest_run_events: FlowEvent[]
  compatibility?: CompatibilityReport
}

export interface FlowEvent {
  state?: string
  type?: string
  message?: string
  data?: {
    action?: string
    output?: string
    input?: string
    skipped?: boolean
    tool_results?: any[]
    [key: string]: any
  }
  error_envelope?: RuntimeErrorEnvelope
  timestamp?: string
  created_at?: string
}

export interface TestProbeRange {
  start_node_id: string
  end_node_id: string
  node_ids: string[]
}

export interface FlowFiles {
  manifest?: string
  root_flow?: string
  welcome?: string
  [key: string]: string | undefined
}

export type AIFlowStewardMode = 'guided' | 'delegated'

export interface AIFlowSelection {
  node_ids: string[]
  edge_ids: string[]
  field_paths: string[]
}

export interface AIFlowStewardContext {
  tool: 'none' | 'pointer' | 'lasso'
  view: 'engineering' | 'outcome'
  revision: string
  selection: AIFlowSelection
  scope_policy: 'selected_and_direct_edges' | 'single_anchor'
}

export interface AIFlowStewardMessage {
  mode: AIFlowStewardMode
  understanding: string
  answer: string
  selection_revision: string
  scope: AIFlowSelection
  operations: Array<{ op: string; target: string; description: string }>
  validation: { checks: string[] }
  risk: 'none' | 'low' | 'medium' | 'high'
  confirmation_required: boolean
  next_step: string
}

export interface CartridgeAsset {
  id: string
  kind: string
  path: string
  media_type: string
  sha256: string
  size: number
  executable: false
  content?: string
  encoding?: string
}

export interface InteractionComponent {
  id: string
  version: string
  runtime: 'passive' | 'sandboxed'
  entry: { type: 'asset'; ref: string }
  supported_modes: Array<'display' | 'collect' | 'review'>
  input_schema?: Record<string, any> | string
  actions: Array<{ id: string; label?: string; payload_schema?: Record<string, any> | string }>
  host_capabilities?: string[]
}

export interface CartridgeAssetsResponse {
  cartridge_id: string
  assets: CartridgeAsset[]
  components: InteractionComponent[]
  files: FlowFiles
}

export interface McpTool {
  id: string
  name: string
  type: 'builtin' | 'mcp' | string
  server: string
  tool: string
  description?: string
  default_params?: Record<string, any>
  params_schema?: Record<string, any>
  required?: boolean
  contract?: Record<string, any>
  enabled?: boolean
  node_id?: string
  transparency?: string
  source_digest?: string
}

export interface McpSourceModel {
  schema: 'cartridgeflow.mcp_source_model.v1' | string
  ok: boolean
  node_id: string
  tool_identity: string
  format: string
  source: { path: string; sha256: string; line_count: number }
  operations: Array<Record<string, any> & { id: string }>
  edges: Array<Record<string, any>>
  fallbacks: Array<Record<string, any>>
  inputs: Record<string, any>
  outputs: Record<string, any>
  capabilities: string[]
  source_map: Record<string, any>
  findings: Array<{ severity: string; code: string; message: string; line?: number }>
  source_digest: string
}

export interface McpSourceResponse {
  node_id: string
  path: string
  source: string
  source_digest: string
  source_model: McpSourceModel
}

export interface McpSourceEditResponse {
  status: string
  source: string
  source_model: McpSourceModel
  source_digest: string
  files: FlowFiles
  mcp_tools: McpTool[]
}

export interface BaseImplementationResponse {
  ok: boolean
  base: any
  protocol_catalog?: ProtocolReleaseCatalog
}

export interface ProtocolReleaseCatalog {
  schema: string
  base_contract: { id: string; version: string }
  default_for_new_flows: { id: string; version: string; label: string }
  releases: Array<{ id: string; version: string; lifecycle: string; migration_target?: { id: string; version: string } }>
}

export interface StudioConformanceResponse {
  available: boolean
  report_path?: string
  command?: string
  report?: {
    schema: string
    status: string
    generated_at: string
    tests: { status: string; total: number; counts: Record<string, number> }
    capabilities: { status: string; declared: number; counts: Record<string, number>; items?: any[] }
  }
}

export interface CompatibilityFinding {
  severity: 'blocker' | 'warning' | 'info' | string
  code: string
  message: string
}

export interface CompatibilityReport {
  ok: boolean
  status: string
  legacy?: boolean
  base?: any
  cartridge?: any
  protocol?: any
  profiles?: any
  capabilities?: any
  tools?: any
  delivery_readiness?: any
  summary?: { blocker?: number; warning?: number; info?: number }
  findings?: CompatibilityFinding[]
}

export interface ProtocolCertificationReport {
  ok: boolean
  status: string
  label?: string
  protocol?: any
  base?: any
  cartridge?: any
  compatibility?: CompatibilityReport
  summary?: { blocker?: number; warning?: number; info?: number }
  findings?: CompatibilityFinding[]
}

export interface McpToolsResponse {
  cartridge_id: string
  mcp_tools: McpTool[]
  files: FlowFiles
}

export interface ValidationResponse {
  valid: boolean
  errors: string[]
  warnings: string[]
  summary?: string
}

export interface NodeUpdateResult {
  status: string
  node_id: string
  files: FlowFiles
  validation: ValidationResponse
  graph: FlowGraph
}

export interface TuningRevision {
  id: string
  node_id: string
  parent_id?: string | null
  flow_digest: string
  patch: Record<string, any>
  author: string
  message: string
  created_at: string
  digest: string
}

export interface RecipeRelease {
  id: string
  sequence: number
  status: 'published'
  flow_digest: string
  node_revisions: Record<string, string>
  patches: Record<string, Record<string, any>>
  created_at: string
  created_by: string
  message: string
  digest: string
}

export interface TuningRepository {
  schema: 'cartridgeflow.tuning_repository.v1'
  protocol: { id: 'CF-TUNING'; version: '1.0' }
  flow_id: string
  repository_revision: number
  node_heads: Record<string, string>
  revisions: TuningRevision[]
  releases: RecipeRelease[]
  active_release_id?: string | null
}

export interface TuningContext {
  mode: 'draft' | 'published'
  protocol: { id: string; version: string }
  release_id?: string | null
  active_release_id?: string | null
  release_digest?: string | null
  flow_digest: string
  node_revisions: Record<string, string>
  repository_revision?: number | null
  materialization_digest: string
}

export interface TuningResponse {
  repository: TuningRepository
  tuning_context?: TuningContext | null
}

export interface TuningRevisionResult extends NodeUpdateResult {
  revision: TuningRevision
  repository: TuningRepository
  tuning_context: TuningContext
}

export interface RecipeReleaseResult {
  status: string
  release: RecipeRelease
  repository: TuningRepository
}

export interface NodeCreatePayload {
  files: FlowFiles
  template_id: string
  node_id: string
  title?: string
  after_node_id?: string
  insert_mode?: 'insert' | 'branch'
  node?: Record<string, any>
}

// ── LLM Provider 相关类型 ──────────────────────────────────────────────
export interface LlmProvider {
  id: string
  name: string
  api_type: string
  base_url?: string
  default_model?: string
  wire_api?: string
  capabilities?: string[]
  available_models?: string[]
  adapter_profile?: string
  adapter_label?: string
  adapter_supported?: boolean
  enabled?: boolean
  timeout?: number
  has_key?: boolean
  key_preview?: string
  tested_ok?: boolean
  tested_at?: string
  runtime_supported?: boolean
  runtime_issue?: string
  source?: string
}

export interface LlmAssignment {
  provider_id?: string
  model?: string
}

export interface LlmAssignments {
  version: number
  defaults: Record<string, LlmAssignment>
  cartridges: Record<string, Record<string, LlmAssignment>>
  nodes: Record<string, Record<string, LlmAssignment>>
}

export interface LlmConfigBundle {
  version: number
  providers: LlmProvider[]
  assignments: LlmAssignments
}

export interface LlmDetectionResult {
  ok: boolean
  status: string
  provider: {
    name: string
    api_type: string
    base_url: string
    default_model: string
    wire_api: string
    capabilities: string[]
    adapter_profile: string
    timeout: number
  }
  detection: {
    capability: string
    adapter_label: string
    confidence: string
    model_count: number
    models: string[]
    models_endpoint: string
    summary: string
  }
  used_stored_key?: boolean
}

export interface LlmTestResult {
  ok: boolean
  provider_id?: string
  model?: string
  content?: string
  capability?: string
  adapter_profile?: string
  tested_scope?: string
  error?: string
  status_code?: number
  retryable?: boolean
}

export interface StudioToolResource {
  id: string
  name: string
  kind: 'builtin' | 'mcp' | 'remote_api' | 'plugin' | string
  description?: string
  endpoint?: string
  command?: string
  args?: string
  openapi_url?: string
  http_method?: 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE' | string
  auth_env?: string
  auth_header?: string
  auth_scheme?: string
  capabilities?: string[]
  read_only?: boolean
  package_mode?: 'base' | 'descriptor' | 'external' | string
  enabled?: boolean
  locked?: boolean
  server?: string
  tool?: string
  resource_id?: string
  source?: 'base_builtin' | 'local_resource' | 'cartridge_dlc' | string
  owner?: string
  status?: 'ready' | 'available' | 'unbound' | 'unavailable' | string
  flow_binding?: { bound: boolean; status: string }
  manifest_requirement?: { declared: boolean; required: boolean }
  node_references?: string[]
  transparency?: string
  node_id?: string
  implementation?: Record<string, any>
  source_digest?: string
  parse_status?: 'parsed' | 'opaque' | 'not_applicable' | string
  presentation_mode?: McpPresentationMode
  readability?: McpReadability
  connector?: McpConnector | null
  contract?: McpCallContract
  health?: McpResourceHealth
  operation_count?: number
  broker_capabilities?: string[]
  operation_graph?: {
    operations?: Array<Record<string, any>>
    edges?: Array<Record<string, any>>
    fallbacks?: Array<Record<string, any>>
    capabilities?: string[]
  }
}

export type McpPresentationMode = 'local_parsable' | 'external_connector' | 'unauditable' | string

export interface McpReadability {
  state: 'readable' | 'not_readable' | string
  reason?: string | null
}

export interface McpConnectionReference {
  state: 'configured' | 'not_configured' | string
  reference?: string | null
  transport?: string | null
}

export interface McpConnectorAuthentication {
  required: boolean
  reference?: string | null
  status: 'configured' | 'missing' | 'not_required' | string
}

export interface McpConnector {
  id: string
  identity: string
  kind: string
  endpoint: McpConnectionReference
  openapi: McpConnectionReference
  command: McpConnectionReference
  authentication: McpConnectorAuthentication
}

export interface McpCallContract {
  server?: string
  tool?: string
  input_schema?: Record<string, any>
  output_schema?: Record<string, any>
  permissions?: string[]
  read_only?: boolean
  side_effect?: string
  timeout_ms?: number
  retry?: Record<string, any>
  idempotency?: {
    declared?: boolean | null
    status?: 'idempotent' | 'non_idempotent' | 'unknown' | string
  }
}

export interface McpConnectionHealth {
  status: string
  checked_at?: string | null
  code?: string
  message?: string
  retryable?: boolean | null
  adapter?: string | null
  http_status?: number | null
}

export interface McpRunHealth {
  status: string
  last_run_at?: string | null
  code?: string
  message?: string
}

export interface McpResourceHealth {
  connection: McpConnectionHealth
  run: McpRunHealth
}

export interface FlowResourceDetail {
  schema: 'cartridgeflow.flow_resource_detail.v1' | string
  cartridge_id: string
  resource: StudioToolResource
}

export interface FlowResourceConnectivityResult {
  schema: 'cartridgeflow.flow_resource_connectivity.v1' | string
  cartridge_id: string
  resource_id: string
  ok: boolean
  connection_health: McpConnectionHealth
}

export interface StudioResources {
  version: number
  tools: StudioToolResource[]
  bindings: {
    roles?: Record<string, Record<string, string>>
    tools?: Record<string, string[]>
  }
  builtin_tools: StudioToolResource[]
}

export interface FlowResourceCatalog {
  schema: 'cartridgeflow.flow_resource_catalog.v1' | 'cartridgeflow.flow_resource_catalog.v2' | string
  cartridge_id: string
  tools: StudioToolResource[]
  models: {
    providers: LlmProvider[]
    runtime_roles: any[]
    flow_bindings: Record<string, { provider_id?: string; model?: string }>
    node_bindings: Array<{ node_id: string; role: string; binding?: { provider_id?: string; model?: string } | null; status: string }>
    authoring: { scope: 'base_authoring' | string; bindings: Record<string, { provider_id?: string; model?: string }> }
  }
  findings: Array<{ severity: string; code: string; message: string; path?: string; node_ids?: string[] }>
  summary: { tools: number; ready: number; referenced: number; blockers: number }
}

export interface StudioCredential {
  key: string
  label: string
  secret: boolean
  source: 'local' | 'process' | string
  has_value: boolean
  preview: string
  updated_at?: string
}

export interface StudioEnvironmentReference {
  key: string
  label: string
  owners: string[]
  configured: boolean
}

export interface StudioSystemCheck {
  id: string
  label: string
  status: 'ok' | 'warning' | 'missing' | 'blocked' | string
  version: string
  path: string
}

export interface StudioEnvironmentSnapshot {
  credentials: StudioCredential[]
  references: StudioEnvironmentReference[]
  checks: StudioSystemCheck[]
  paths: Record<string, string>
}

export interface StudioPackageItem {
  filename: string
  url: string
  size: number
  modified_at: string
  cartridge_id: string
  name: string
  version: string
  package_mode: string
  protocol?: string
  release_id?: string
}

export interface PortabilityReport {
  schema: 'cartridgeflow.portability_report.v1' | string
  status: 'ok' | 'blocked' | string
  summary: {
    portable: number
    local_rebind: number
    missing_blockers: number
    forbidden: number
    scanned_files: number
  }
  portable: any[]
  local_rebind: any[]
  missing_blockers: any[]
  forbidden: any[]
}

export interface StudioReleasePreflight {
  cartridge: { id: string; name: string; version: string; source: string; editable: boolean }
  compatibility: CompatibilityReport
  certification: ProtocolCertificationReport
  environment: { status: string; summary?: string; items: any[] }
  dependencies: { status: string; summary?: string; items: any[] }
  models: { status: string; items: any[] }
  resources: { status: string; items: any[]; descriptor?: any }
  package_hygiene: { status: string; items: any[]; scanned_files?: number }
  portability: PortabilityReport
  release_envelope: {
    protocol: string
    status: 'ready' | 'blocked' | string
    base_supported: boolean
    report: { ok: boolean; findings: any[]; summary?: Record<string, number> }
  }
  issues: { area: string; severity: string; message: string }[]
  dev_ready: boolean
  production_ready: boolean
}

// ── 卡带 API ──────────────────────────────────────────────
