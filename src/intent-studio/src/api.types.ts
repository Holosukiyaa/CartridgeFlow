export interface CreatorFieldContract {
  id: string
  label: string
  value_type: 'string' | 'string_list' | 'boolean' | 'number'
  required: boolean
  default: unknown
}

export interface CreatorRecipeNode {
  id: string
  label: string
  description: string
  preset?: { id: string; revision: number; digest: string }
  values: Record<string, unknown>
  editable_fields: CreatorFieldContract[]
  resolution?: {
    status: 'resolved' | 'unresolved'
    needed_capability: string
    capability?: {
      id: string
      revision: number
      digest: string
      trust_scope: 'system' | 'organization' | 'workspace'
      label: string
      description: string
    }
  }
  experience?: {
    status: 'available' | 'unavailable'
    reason?: string
    slots: Array<{
      id: string
      label: string
      status: 'configured' | 'configuration_required'
      selected_component_id: string
      field_sources: Record<string, string>
      sources: Array<{ id: string; label: string; schema: Record<string, unknown> }>
      components: Array<{
        id: string
        label: string
        description: string
        available: boolean
        preview_html: string
        fields: Array<{
          id: string
          label: string
          required: boolean
          compatible_source_ids: string[]
        }>
      }>
    }>
  }
}

export interface CreatorProposal {
  proposal_id: string
  revision: number
  summary: string
  changes: Array<{ id: string; target_id: string; operation: string; value?: unknown }>
}

export interface CreatorProjection {
  project_id: string
  project_name?: string
  session_id: string
  revision: number
  experience_revision?: number
  intent: string
  trusted_recipe: {
    id: string
    goal: string
    nodes: CreatorRecipeNode[]
    relations: Array<{ id: string; from_node_id: string; to_node_id: string; relation: string }>
  }
  frozen_steps: string[]
  active_freezes: Array<{
    id: string
    steps: string[]
    freeze_revision: { source_freeze_ids: string[]; expected_revision: number }
  }>
  pending_proposals: CreatorProposal[]
  generation_readiness: { ready: boolean }
  capability_resolution?: { resolved: number; unresolved: number; revision: number }
}

export interface CreatorSourceCandidate {
  id: string
  name: string
  provides: string
  why_recommended: string
  risk: string
  review_focus: string
  remote_url: string
  rss_url: string
}

export interface CreatorRecipePreview {
  proposal_id: string
  goal: string
  nodes: Array<{ id: string; label: string; description: string; resolution: 'resolved' | 'unresolved' }>
  relations: Array<{ id: string; from_node_id: string; to_node_id: string; relation: string }>
  impact: { added_node_ids: string[]; removed_node_ids: string[]; retained_node_ids: string[] }
}

export interface CreatorPossibility {
  id: string
  title: string
  outcome: string
  why_it_fits: string
  first_week_output: string
  needs_confirmation: string[]
  recipe: {
    intent: string
    steps: Array<{ id: string; intent: string; inputs: []; outputs: [] }>
  }
}

export interface CreatorClarification {
  question: string
  why_it_matters: string
  suggested_answers: string[]
}

export interface CreatorDiscoveryResult {
  schema: 'cartridgeflow.creator_discovery.v2'
  context: string
  output_locale: 'zh-CN'
  mode: 'clarify' | 'propose'
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
}

export interface CreatorProposalPreview {
  accepted_change_ids: string[]
  impact: { plain_summary?: string; changed_steps?: string[]; changed_sources?: string[] }
}

export interface CreatorPackage {
  schema: 'cartridgeflow.creator_package.v1'
  status: 'ready'
  filename: string
  url: string
  signature_verified: boolean
}
