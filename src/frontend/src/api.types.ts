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
}

export interface CreatorProposal {
  proposal_id: string
  revision: number
  summary: string
  changes: Array<{ id: string; target_id: string; operation: string; value?: unknown }>
}

export interface CreatorProjection {
  project_id: string
  session_id: string
  revision: number
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
