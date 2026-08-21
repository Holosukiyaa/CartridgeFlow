export const NARROW_QUERY = '(max-width: 960px)'
export const COMPOSE_INPUT_ID = 'studio-goal-input'
export const MIN_GOAL_LENGTH = 3
export const WORKSPACE_SNAPSHOT_VERSION = 1 as const
export const RUNNER_FALLBACK_URL = 'http://127.0.0.1:18990/'
export const SAVE_DEBOUNCE_MS = 700
export type LlmPreset = {
  id: string
  label: string
  badge?: string
  baseUrl: string
  model: string
}

export const LLM_PRESETS: LlmPreset[] = [
  { id: 'deepseek', label: 'DeepSeek', badge: '推荐', baseUrl: 'https://api.deepseek.com/v1', model: 'deepseek-chat' },
  { id: 'openai', label: 'OpenAI', baseUrl: 'https://api.openai.com/v1', model: 'gpt-5-mini' },
  { id: 'local', label: '本机', badge: '离线', baseUrl: 'http://127.0.0.1:11434/v1', model: '' },
  { id: 'custom', label: '自定义', baseUrl: '', model: '' },
]

export const THEMES = [
  { id: 'light', label: '浅色' },
  { id: 'dark', label: '深色' },
] as const

export const SHELL_TABS = [
  { id: 'steward', label: '管家' },
  { id: 'canvas', label: '画布' },
  { id: 'detail', label: '详情' },
] as const

export type ShellTabId = (typeof SHELL_TABS)[number]['id']

export const AUTHORING_PROVIDER_ID = 'creator-ai'
export const LAYOUT_KEY = 'cartridgeflow.studio.layout.v1'
export const RELATION_KIND_FILTERS = [
  { id: 'control', label: '主流程' },
  { id: 'data', label: '数据' },
  { id: 'uses', label: '能力' },
] as const
export const TOOL_KINDS = [
  { id: 'mcp', label: 'MCP 工具' },
  { id: 'remote_api', label: '远程接口' },
  { id: 'plugin', label: '插件' },
] as const

export const L2_STAGES = [
  { id: 'flow', index: '01', label: '内部怎么走' },
  { id: 'result', index: '02', label: '结果长什么样' },
  { id: 'prove', index: '03', label: '用真样本证明' },
  { id: 'publish', index: '04', label: '发布回第一层' },
] as const

export type Layer2StageId = (typeof L2_STAGES)[number]['id']
