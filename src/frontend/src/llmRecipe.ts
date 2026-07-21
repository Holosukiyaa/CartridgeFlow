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
  const missing = [
    !provider.base_url ? 'URL' : '',
    !provider.has_key ? 'Key' : '',
  ].filter(Boolean)
  if (missing.length) return { ...role, provider, state: 'missing', message: `本机缺少 ${missing.join(' / ')}` }
  if (role.api_type && provider.api_type !== role.api_type) {
    return { ...role, provider, state: 'mismatch', message: `需要 ${role.api_type}，当前为 ${provider.api_type}` }
  }
  if (role.wire_api && provider.wire_api && provider.wire_api !== role.wire_api) {
    return { ...role, provider, state: 'mismatch', message: `需要 ${role.wire_api}` }
  }
  return { ...role, provider, state: 'ready', message: `已连接 ${provider.name}` }
}

export function findExactProviderMatch(role: LlmRecipeRole, providers: LlmProvider[]): LlmProvider | undefined {
  const normalize = (value: string) => value.trim().toLocaleLowerCase()
  const roleNames = [role.label, role.id].map(normalize).filter(Boolean)
  return providers.find((provider) => roleNames.includes(normalize(provider.name)) || roleNames.includes(normalize(provider.id)))
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
