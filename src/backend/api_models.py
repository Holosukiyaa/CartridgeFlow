"""Request payload models for the CartridgeFlow HTTP API."""

from pydantic import BaseModel, ConfigDict, Field

class CartridgeRunCreate(BaseModel):
    cartridge_id: str
    inputs: dict = Field(default_factory=dict)
    test_mode: dict | None = None


class CartridgeRunControl(BaseModel):
    action: str
    target_node: str | None = None
    confirm_side_effect: bool = False
    feedback: dict = Field(default_factory=dict)


class PendingInteractionAnswerPayload(BaseModel):
    values: dict = Field(default_factory=dict)
    answer: str | None = None
    action_id: str | None = None
    input_revision: str | int | None = None
    idempotency_key: str | None = None
    draft_hash: str | None = None


class SandboxHostRequestPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    schema_: str = Field(alias="schema")
    type: str
    request_id: str
    channel_id: str
    run_id: str
    cartridge_id: str
    node_id: str
    component_id: str
    interaction_id: str
    nonce: str
    payload: dict = Field(default_factory=dict)

class DevFlowCreate(BaseModel):
    flow_id: str
    name: str
    description: str = ""


class AuthoringSimulationPayload(BaseModel):
    keep_temporary_cartridge: bool = False


class CartridgeCloneToDevPayload(BaseModel):
    new_id: str
    name: str = ""
    description: str = ""


class DevFlowFileSave(BaseModel):
    content: str


class DevFlowFilesPayload(BaseModel):
    files: dict = Field(default_factory=dict)


class TuningRevisionPayload(BaseModel):
    patch: dict = Field(default_factory=dict)
    expected_head: str | None = None
    author: str = "local-developer"
    message: str = "更新关键参数"


class RecipeReleasePayload(BaseModel):
    author: str = "local-developer"
    message: str = "发布配方版本"


class FlowAnalysisPayload(DevFlowFilesPayload):
    target: str = "draft"


class AIFlowSelection(BaseModel):
    node_ids: list[str] = Field(default_factory=list)
    edge_ids: list[str] = Field(default_factory=list)
    field_paths: list[str] = Field(default_factory=list)


class AIFlowStewardPayload(BaseModel):
    message: str
    mode: str = "guided"
    view: str = "engineering"
    revision: str = ""
    tool: str = "none"
    selection: AIFlowSelection = Field(default_factory=AIFlowSelection)
    scope_policy: str = "selected_and_direct_edges"


class AuthoringSessionCreatePayload(BaseModel):
    session_id: str
    project_id: str | None = None
    recipe_id: str
    intent: str
    steps: list[dict] = Field(default_factory=list)
    source_references: list[dict] = Field(default_factory=list)
    bindings: dict = Field(default_factory=dict)


class CreatorDiscoveryPayload(BaseModel):
    context: str = Field(min_length=3, max_length=2000)


class AuthoringProposalPayload(BaseModel):
    changes: list[dict] = Field(default_factory=list)
    author: str = "creator"
    summary: str
    expected_revision: int


class AuthoringAcceptPayload(BaseModel):
    selected_change_ids: list[str] | None = None
    freeze_revision: dict | None = None


class AuthoringRejectPayload(BaseModel):
    reason: str = ""


class AuthoringReversePayload(BaseModel):
    author: str = "creator"
    summary: str
    expected_revision: int
    freeze_revision: dict | None = None


class AuthoringFreezePayload(BaseModel):
    step_ids: list[str] = Field(default_factory=list)
    author: str = "creator"
    summary: str


class AuthoringAIProposalPayload(BaseModel):
    prompt: str
    expected_revision: int
    author: str = "creator"
    summary: str = "AI-assisted design proposal"


class AuthoringReadinessPayload(BaseModel):
    expected_revision: int


class CreatorHandoffPayload(AuthoringReadinessPayload):
    compile_candidate: dict


class CartridgeAssetPayload(BaseModel):
    id: str
    kind: str
    path: str
    media_type: str
    content: str = ""
    encoding: str = "utf-8"


class InteractionComponentPayload(BaseModel):
    component: dict = Field(default_factory=dict)


class LLMProviderPayload(BaseModel):
    id: str = ""
    name: str = ""
    api_type: str = "openai"
    base_url: str = ""
    api_key: str = ""
    default_model: str = ""
    wire_api: str = "chat_completions"
    capabilities: list[str] = Field(default_factory=list)
    available_models: list[str] = Field(default_factory=list)
    adapter_profile: str = "standard"
    enabled: bool = True
    timeout: int = 120


class LLMAssignmentsPayload(BaseModel):
    version: int = 1
    defaults: dict = Field(default_factory=dict)
    cartridges: dict = Field(default_factory=dict)
    nodes: dict = Field(default_factory=dict)


class LLMTestPayload(BaseModel):
    provider_id: str
    model: str = ""
    prompt: str = "OK"
    vision: bool = False


class LLMDetectPayload(BaseModel):
    provider_id: str = ""
    base_url: str = ""
    api_key: str = ""
    preferred_model: str = ""


class LLMImportTextPayload(BaseModel):
    content: str


class LLMCodexImportPayload(BaseModel):
    config_toml: str
    auth_json: dict = Field(default_factory=dict)


class LLMSimpleProviderPayload(BaseModel):
    provider: str
    api_key: str
    base_url: str = ""
    model: str = ""


class StudioResourcesPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    version: int = 1
    tools: list[dict] = Field(default_factory=list)
    bindings: dict = Field(default_factory=dict)


class StudioCredentialPayload(BaseModel):
    key: str = ""
    label: str = ""
    value: str = ""
    secret: bool = True


class NodeDeletePayload(BaseModel):
    files: dict = Field(default_factory=dict)


class NodeUpdatePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    title: str | None = None
    type: str | None = None
    action: str | None = None
    next: str | None = None
    kind: str | None = None
    executor: str | None = None
    effect: str | None = None
    display_name: str | None = None
    experience: dict | None = None
    component_ref: str | None = None
    interaction_mode: str | None = None
    input_binding: dict | None = None
    action_routes: dict | None = None
    output: str | None = None
    display: dict | None = None
    input_kind: str | None = None
    source: str | None = None
    input_schema: dict | str | None = None
    output_contract: str | None = None
    decision_contract: dict | None = None
    decision_test_mode: str | None = None
    mock_decision_envelope: dict | None = None
    primary_output: str | None = None
    tool_binding: str | None = None
    allowed_tools: list[str] | None = None
    mcp_binding: dict | None = None
    failure_policy: str | None = None
    permission: str | None = None
    audit_log: bool | None = None
    endpoint: str | None = None
    timeout_ms: int | None = None
    agent: str | None = None
    tools: list[dict] | None = None
    params: dict | None = None
    model_role: str | None = None
    layout: dict | None = None
    inputs: dict | None = None
    outputs: dict | None = None
    manifest_inputs: list[dict] | None = None
    manifest_model_roles: list[dict] | None = None


class NodeCreatePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    template_id: str
    node_id: str
    title: str | None = None
    after_node_id: str | None = None
    insert_mode: str = "insert"
    node: NodeUpdatePayload | None = None


class LayoutSavePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    layout: dict = Field(default_factory=dict)  # {node_id: {"x": int, "y": int}}


class EdgeSavePayload(BaseModel):
    files: dict = Field(default_factory=dict)
    edges: list[dict] = Field(default_factory=list)  # [{"from": "a", "to": "b"}]


class AnnotationSavePayload(BaseModel):
    annotations: list[dict] = Field(default_factory=list)


class McpToolPayload(BaseModel):
    id: str = ""
    name: str = ""
    type: str = "builtin"
    server: str = "filesystem"
    tool: str = ""
    description: str = ""
    default_params: dict = Field(default_factory=dict)
    params_schema: dict = Field(default_factory=dict)
    required: bool = False
    contract: dict = Field(default_factory=dict)
    enabled: bool = True


class McpSourcePatchPayload(BaseModel):
    expected_source_digest: str
    graph: dict = Field(default_factory=dict)


class McpOperationCreatePayload(BaseModel):
    expected_source_digest: str
    operation: dict = Field(default_factory=dict)


class McpSourceReplacePayload(BaseModel):
    expected_source_digest: str
    source: str

class UploadTextPayload(BaseModel):
    filename: str = "upload.txt"
    content: str = ""

class CartridgeImportPayload(BaseModel):
    filename: str = "cartridge.cartridge.zip"
    content_base64: str = ""
    install_mode: str = "keep_existing"

class CartridgePackagePayload(BaseModel):
    package_mode: str = "dev"
