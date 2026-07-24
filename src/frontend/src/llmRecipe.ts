import type { LlmAssignments, LlmProvider } from './api.ts'

export type LlmRecipeRole = {
  id: string
  label: string
  capability: string
  api_type: string
  wire_api: string
  model: string
  required: boolean
}

export type LlmRoleReadiness = LlmRecipeRole & {
  state: 'ready' | 'unbound' | 'missing' | 'mismatch'
  message: string
  provider?: LlmProvider
}

const SUPPORTED_ROUTES = new Set(['openai/chat_completions', 'openai/responses'])

function normalizeCapability(value?: string) {
  const normalized = String(value || '').trim().toLowerCase().replaceAll('-', '_')
  return ({ text_generation: 'text_reasoning', image_generation_tool: 'image_generation' } as Record<string, string>)[normalized] || normalized
}

export function normalizeProviderApiType(value?: string) {
  const normalized = String(value || 'openai').trim().toLowerCase().replaceAll('-', '_')
  if (normalized === 'openai_compatible' || normalized === 'openai_api') return 'openai'
  if (normalized === 'claude') return 'anthropic'
  return normalized
}

export function normalizeProviderWireApi(value?: string, apiType?: string) {
  const fallback = normalizeProviderApiType(apiType) === 'anthropic' ? 'messages' : 'chat_completions'
  const normalized = String(value || fallback).trim().toLowerCase().replaceAll('-', '_').replaceAll('.', '_')
  if (normalized === 'chat_completion' || normalized === 'chatcompletions') return 'chat_completions'
  return normalized
}

export function providerRouteIssue(provider: LlmProvider) {
  if (provider.runtime_supported === false && provider.runtime_issue) return provider.runtime_issue
  const apiType = normalizeProviderApiType(provider.api_type)
  const wireApi = normalizeProviderWireApi(provider.wire_api, apiType)
  if (SUPPORTED_ROUTES.has(`${apiType}/${wireApi}`)) return ''
  return apiType === 'openai' ? `当前底座尚未实现 OpenAI ${wireApi}` : `当前底座尚未实现 ${apiType} 模型适配器`
}

export function providerRoleCompatibilityIssue(role: LlmRecipeRole, provider: LlmProvider) {
  const routeIssue = providerRouteIssue(provider)
  if (routeIssue) return routeIssue
  if (role.api_type && normalizeProviderApiType(role.api_type) !== normalizeProviderApiType(provider.api_type)) {
    return `需要 ${role.api_type}`
  }
  if (role.wire_api && normalizeProviderWireApi(role.wire_api, role.api_type) !== normalizeProviderWireApi(provider.wire_api, provider.api_type)) {
    return `需要 ${role.wire_api}`
  }
  if (role.capability && provider.capabilities?.length && !provider.capabilities.map(normalizeCapability).includes(normalizeCapability(role.capability))) {
    return `需要能力 ${role.capability}`
  }
  return ''
}

export function normalizeRecipeRoles(recipe: any): LlmRecipeRole[] {
  if (!recipe || recipe.schema !== 'cartridgeflow.llm_recipe.v1' || !Array.isArray(recipe.roles)) return []
  return recipe.roles
    .filter((role: any) => role && typeof role === 'object' && String(role.id || '').trim())
    .map((role: any) => ({
      id: String(role.id).trim(),
      label: String(role.label || role.id).trim(),
      capability: String(role.capability || 'text_generation').trim(),
      api_type: String(role.api_type || 'openai').trim(),
      wire_api: String(role.wire_api || 'chat_completions').trim(),
      model: String(role.model || '').trim(),
      required: role.required !== false,
    }))
}

export function getRoleReadiness(
  cartridgeId: string,
  role: LlmRecipeRole,
  providers: LlmProvider[],
  assignments: LlmAssignments | null,
): LlmRoleReadiness {
  const binding = assignments?.cartridges?.[cartridgeId]?.[role.id]
  if (!binding?.provider_id) return { ...role, state: 'unbound', message: '未绑定本机 Provider；URL / Key 待填写' }
  const provider = providers.find((item) => item.id === binding.provider_id)
  if (!provider) return { ...role, state: 'missing', message: '本机 Provider 不存在' }
  const compatibilityIssue = providerRoleCompatibilityIssue(role, provider)
  if (compatibilityIssue) return { ...role, provider, state: 'mismatch', message: compatibilityIssue }
  const missing = [
    !provider.base_url ? 'URL' : '',
    !provider.has_key ? 'Key' : '',
    !(binding.model || (role.model !== 'configured-locally' ? role.model : '') || provider.default_model) ? '模型' : '',
  ].filter(Boolean)
  if (missing.length) return { ...role, provider, state: 'missing', message: `本机缺少 ${missing.join(' / ')}` }
  if (role.model && role.model !== 'configured-locally' && binding.model && binding.model !== role.model) {
    return { ...role, provider, state: 'mismatch', message: `需要模型 ${role.model}` }
  }
  return { ...role, provider, state: 'ready', message: provider.tested_ok ? `已验证 ${provider.name}` : `已连接 ${provider.name}，等待验证` }
}

export function findExactProviderMatch(role: LlmRecipeRole, providers: LlmProvider[]): LlmProvider | undefined {
  const normalize = (value: string) => value.trim().toLocaleLowerCase()
  const roleNames = [role.label, role.id].map(normalize).filter(Boolean)
  return providers.find((provider) => (
    roleNames.includes(normalize(provider.name)) || roleNames.includes(normalize(provider.id))
  ) && !providerRoleCompatibilityIssue(role, provider))
}

export function getCartridgeRecipeStatus(
  cartridgeId: string,
  recipe: any,
  providers: LlmProvider[],
  assignments: LlmAssignments | null,
) {
  const roles = normalizeRecipeRoles(recipe).map((role) => getRoleReadiness(cartridgeId, role, providers, assignments))
  if (!roles.length) return { state: 'none', label: '无需模型', roles }
  const required = roles.filter((role) => role.required)
  const unresolved = required.filter((role) => role.state !== 'ready')
  if (unresolved.length) return { state: 'warning', label: `${unresolved.length} 项待连接`, roles }
  return { state: 'ready', label: `${roles.length} 个角色就绪`, roles }
}
