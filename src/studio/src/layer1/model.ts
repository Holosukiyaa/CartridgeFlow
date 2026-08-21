import type { CreatorClarification, CreatorPackage, CreatorPossibility, CreatorProjection, CreatorRecipeNode } from '../api/types.ts'
import type { CreatorRunnerDelivery, DesktopRunnerStatus } from '../api/client.ts'
import { copy } from '../copy.ts'
import { WORKSPACE_SNAPSHOT_VERSION } from '../config.ts'

export type ReviewState = 'confirmed' | 'review' | 'unresolved'
export type StageId = 'connect-ai' | 'describe' | 'clarify' | 'choose' | 'complete-step' | 'prepare-run' | 'run-ready'
export type GuidanceAction = 'connect' | 'compose' | 'open-node' | 'package' | 'deliver' | 'runner' | 'download'

export type Guidance = {
  stage: StageId
  step: number
  title: string
  detail: string
  actionLabel: string
  showAction: boolean
  ready?: boolean
  action: GuidanceAction
  nodeId?: string
}

export type ReviewCounts = {
  confirmed: number
  review: number
  unresolved: number
}

export type WorkspaceSnapshot = {
  version: typeof WORKSPACE_SNAPSHOT_VERSION
  goal: string
  messages: Array<{ id: string; role: 'assistant' | 'user'; text: string }>
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
  selectedId: string
  packageResult: CreatorPackage | null
  packageRevision: number | null
  layer2Flows: Record<string, string>
  runtimeInputs: Record<string, string>
}

export type GuidanceInput = {
  creator: CreatorProjection | null
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
  packageResult: CreatorPackage | null
  connected: boolean | null
  runnerStatus: DesktopRunnerStatus | null
  runnerDelivery: CreatorRunnerDelivery | null
}

export function nodeReviewState(creator: CreatorProjection, node: CreatorRecipeNode): ReviewState {
  if (node.resolution?.status === 'unresolved') return 'unresolved'
  return creator.frozen_steps.includes(node.id) ? 'confirmed' : 'review'
}

export function statusCopy(state: ReviewState) {
  return state === 'confirmed' ? copy.confirmed : state === 'unresolved' ? copy.unresolved : copy.review
}

export function reviewCounts(creator: CreatorProjection): ReviewCounts {
  return {
    confirmed: creator.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'confirmed').length,
    review: creator.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'review').length,
    unresolved: creator.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'unresolved').length,
  }
}

export function nextUnconfirmed(creator: CreatorProjection) {
  return creator.trusted_recipe.nodes.find((node) => nodeReviewState(creator, node) !== 'confirmed') || null
}

export function requiredFieldsEmpty(node: CreatorRecipeNode, values: Record<string, unknown>) {
  return node.editable_fields.some((field) => {
    if (!field.required || field.value_type === 'boolean') return false
    const value = values[field.id]
    if (Array.isArray(value)) return value.length === 0
    return value == null || String(value).trim() === ''
  })
}

export function workshopReturnFromLocation() {
  const params = new URLSearchParams(window.location.search)
  return {
    nodeId: params.get('nodeId') || '',
    published: params.get('capabilityPublished') || '',
  }
}

export function clearWorkshopReturn() {
  const url = new URL(window.location.href)
  url.searchParams.delete('capabilityPublished')
  url.searchParams.delete('nodeId')
  window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`)
}

export function trustCopy(scope: string | undefined) {
  if (scope === 'workspace') return copy.trustWorkspace
  if (scope === 'organization') return copy.trustOrg
  return copy.trustSystem
}

const rules: Array<(input: GuidanceInput) => Guidance | null> = [
  ({ connected }) => connected === false ? {
    stage: 'connect-ai', step: 1, title: copy.guidance.connectTitle, detail: copy.guidance.connectDetail,
    actionLabel: copy.guidance.connectAction, showAction: true, action: 'connect',
  } : null,
  ({ creator, clarification }) => !creator && clarification ? {
    stage: 'clarify', step: 2, title: copy.guidance.clarifyTitle, detail: clarification.question,
    actionLabel: copy.guidance.clarifyAction, showAction: false, action: 'compose',
  } : null,
  ({ creator, possibilities }) => !creator && possibilities.length ? {
    stage: 'choose', step: 3, title: copy.guidance.chooseTitle, detail: copy.guidance.chooseDetail,
    actionLabel: copy.guidance.chooseAction, showAction: false, action: 'compose',
  } : null,
  ({ creator }) => !creator ? {
    stage: 'describe', step: 2, title: copy.guidance.describeTitle, detail: copy.guidance.describeDetail,
    actionLabel: copy.composeSubmit, showAction: false, action: 'compose', ready: true,
  } : null,
  ({ creator }) => {
    if (!creator) return null
    const next = nextUnconfirmed(creator)
    if (!next) return null
    const gap = nodeReviewState(creator, next) === 'unresolved'
    return {
      stage: 'complete-step',
      step: 4,
      title: gap ? copy.guidance.completeGap(next.label) : next.label,
      detail: creator.intent,
      actionLabel: gap ? copy.guidance.startGap : copy.guidance.reviewNode(next.label),
      showAction: true,
      action: 'open-node',
      nodeId: next.id,
    }
  },
  ({ creator, packageResult }) => creator && !packageResult ? {
    stage: 'prepare-run', step: 5, title: copy.guidance.prepareTitle, detail: creator.intent,
    actionLabel: copy.guidance.prepareAction, showAction: true, action: 'package',
  } : null,
  ({ runnerDelivery }) => runnerDelivery?.status === 'trust_required' ? {
    stage: 'run-ready', step: 5, title: copy.guidance.trustTitle, detail: copy.guidance.trustDetail,
    actionLabel: copy.guidance.trustAction, showAction: true, action: 'runner',
  } : null,
  ({ runnerDelivery }) => runnerDelivery ? {
    stage: 'run-ready', step: 5, title: copy.guidance.installedTitle, detail: copy.guidance.installedDetail,
    actionLabel: copy.guidance.openRunner, showAction: true, action: 'runner',
  } : null,
  ({ runnerStatus }) => runnerStatus?.available ? {
    stage: 'run-ready', step: 5, title: copy.guidance.runnerReadyTitle, detail: copy.guidance.runnerReadyDetail,
    actionLabel: copy.guidance.deliverAction, showAction: true, action: 'deliver',
  } : null,
  () => ({
    stage: 'run-ready', step: 5, title: copy.guidance.downloadTitle, detail: copy.guidance.downloadDetail,
    actionLabel: copy.guidance.downloadAction, showAction: true, action: 'download',
  }),
]

export function resolveGuidance(input: GuidanceInput): Guidance {
  for (const rule of rules) {
    const hit = rule(input)
    if (hit) return hit
  }
  return rules[rules.length - 1](input) as Guidance
}

export function emptyWorkspaceSnapshot(): WorkspaceSnapshot {
  return {
    version: WORKSPACE_SNAPSHOT_VERSION,
    goal: '',
    messages: [],
    clarification: null,
    possibilities: [],
    selectedId: '',
    packageResult: null,
    packageRevision: null,
    layer2Flows: {},
    runtimeInputs: {},
  }
}
