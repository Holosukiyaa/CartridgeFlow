import type { AnyRecord } from './model'

export type CartridgeSettingType = 'string' | 'integer' | 'number' | 'enum' | 'boolean' | 'file' | 'array' | 'object'

export type SettingOption = { value: string | number; label: string }

export type NodeSettingDraft = {
  param: string
  exposed: boolean
  id: string
  label: string
  description: string
  type: CartridgeSettingType
  required: boolean
  sensitive: boolean
  optionsText: string
  source?: AnyRecord
}

export type PresentationFiles = {
  settings_contract?: unknown
  settings_bindings?: unknown
  ui_contract?: unknown
}

const SETTINGS_SCHEMA = 'cartridgeflow.cartridge_settings.v1'
const BINDINGS_SCHEMA = 'cartridgeflow.cartridge_settings_bindings.v1'
const UI_SCHEMA = 'cartridgeflow.cartridge_ui.v1'
const settingTypes = new Set<CartridgeSettingType>(['string', 'integer', 'number', 'enum', 'boolean', 'file', 'array', 'object'])
const identifier = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const parameter = /^[A-Za-z_][A-Za-z0-9_]{0,127}$/

const object = (value: unknown): AnyRecord | null => value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : null

function parseDocument(value: unknown, fallback: AnyRecord, label: string, errors: string[]): AnyRecord {
  if (value === undefined || value === null || value === '') return fallback
  if (object(value)) return value as AnyRecord
  if (typeof value !== 'string') {
    errors.push(`${label}必须是 JSON 对象。`)
    return fallback
  }
  try {
    const parsed = object(JSON.parse(value))
    if (!parsed) errors.push(`${label}必须是 JSON 对象。`)
    return parsed || fallback
  } catch {
    errors.push(`${label}不是有效的 JSON。`)
    return fallback
  }
}

function parsePresentation(files: PresentationFiles) {
  const errors: string[] = []
  const settings = parseDocument(files.settings_contract, { schema: SETTINGS_SCHEMA, storage_scope: 'cartridge', fields: [] }, '公开设置合同', errors)
  const bindings = parseDocument(files.settings_bindings, { schema: BINDINGS_SCHEMA, bindings: [] }, '私有绑定合同', errors)
  if (settings.schema !== SETTINGS_SCHEMA || settings.storage_scope !== 'cartridge' || !Array.isArray(settings.fields)) {
    errors.push('公开设置合同必须使用 cartridge_settings.v1。')
  }
  if (bindings.schema !== BINDINGS_SCHEMA || !Array.isArray(bindings.bindings)) {
    errors.push('私有绑定合同必须使用 cartridge_settings_bindings.v1。')
  }
  return { settings, bindings, errors }
}

function inferredType(value: unknown): CartridgeSettingType {
  if (typeof value === 'boolean') return 'boolean'
  if (typeof value === 'number') return Number.isInteger(value) ? 'integer' : 'number'
  if (Array.isArray(value)) return 'array'
  if (object(value)) return 'object'
  return 'string'
}

function optionLines(value: unknown): string {
  return Array.isArray(value)
    ? value.flatMap((item) => {
        const option = object(item)
        return option && (typeof option.value === 'string' || typeof option.value === 'number') && typeof option.label === 'string'
          ? [`${String(option.value)} | ${option.label}`]
          : []
      }).join('\n')
    : ''
}

export function parseSettingOptions(value: string): SettingOption[] {
  return value.split(/\r?\n/).map((line) => line.trim()).filter(Boolean).map((line) => {
    const separator = line.indexOf('|')
    const rawValue = (separator >= 0 ? line.slice(0, separator) : line).trim()
    const label = (separator >= 0 ? line.slice(separator + 1) : line).trim()
    const optionValue = /^-?(?:\d+\.?\d*|\.\d+)$/.test(rawValue) ? Number(rawValue) : rawValue
    return { value: optionValue, label: label || rawValue }
  })
}

export function nodeSettingDrafts(files: PresentationFiles, nodeId: string, params: AnyRecord): { drafts: NodeSettingDraft[]; errors: string[] } {
  const parsed = parsePresentation(files)
  if (parsed.errors.length) return { drafts: [], errors: parsed.errors }
  const fields = new Map(
    (parsed.settings.fields as unknown[])
      .map(object)
      .filter((item): item is AnyRecord => Boolean(item && typeof item.id === 'string'))
      .map((item) => [String(item.id), item]),
  )
  const boundByParam = new Map<string, AnyRecord>()
  for (const rawBinding of parsed.bindings.bindings as unknown[]) {
    const binding = object(rawBinding)
    const target = object(binding?.target)
    if (!binding || !target || String(target.node_id) !== nodeId || target.kind !== 'process_param') continue
    boundByParam.set(String(target.param || ''), binding)
  }
  const paramNames = [...new Set([...Object.keys(params), ...boundByParam.keys()])].filter((name) => parameter.test(name)).sort()
  return {
    errors: [],
    drafts: paramNames.map((param) => {
      const binding = boundByParam.get(param)
      const field = binding ? fields.get(String(binding.setting_id || '')) : undefined
      const type = settingTypes.has(String(field?.type) as CartridgeSettingType)
        ? String(field?.type) as CartridgeSettingType
        : inferredType(params[param])
      return {
        param,
        exposed: Boolean(field),
        id: String(field?.id || `${nodeId}.${param}`),
        label: String(field?.label || param.replaceAll('_', ' ')),
        description: String(field?.description || ''),
        type,
        required: field?.required === true,
        sensitive: field?.sensitive === true,
        optionsText: optionLines(field?.options),
        source: field,
      }
    }),
  }
}

export function buildNodePresentationFiles(
  files: PresentationFiles,
  nodeId: string,
  params: AnyRecord,
  drafts: NodeSettingDraft[],
): Record<string, string> {
  const parsed = parsePresentation(files)
  if (parsed.errors.length) throw new Error(parsed.errors[0])
  const bindings = (parsed.bindings.bindings as unknown[]).map(object).filter((item): item is AnyRecord => Boolean(item))
  const removedIds = new Set(bindings.flatMap((binding) => {
    const target = object(binding.target)
    return target?.node_id === nodeId ? [String(binding.setting_id || '')] : []
  }))
  const nextBindings = bindings.filter((binding) => object(binding.target)?.node_id !== nodeId)
  const nextFields = (parsed.settings.fields as unknown[]).map(object).filter((item): item is AnyRecord => Boolean(item) && !removedIds.has(String(item?.id || '')))
  const ids = new Set(nextFields.map((field) => String(field.id)))

  for (const draft of drafts.filter((item) => item.exposed)) {
    if (!identifier.test(draft.id)) throw new Error(`设置 ID“${draft.id}”不是稳定标识符。`)
    if (!parameter.test(draft.param)) throw new Error(`参数“${draft.param}”不能绑定为运行设置。`)
    if (!draft.label.trim()) throw new Error(`参数“${draft.param}”缺少显示名称。`)
    if (ids.has(draft.id)) throw new Error(`设置 ID“${draft.id}”已被其他节点使用。`)
    if (!settingTypes.has(draft.type)) throw new Error(`设置“${draft.label}”使用了未发布的控件类型。`)
    const field: AnyRecord = { ...(draft.source || {}), id: draft.id, label: draft.label.trim(), type: draft.type }
    delete field.control
    delete field.placeholder
    delete field.unit
    if (draft.description.trim()) field.description = draft.description.trim(); else delete field.description
    if (draft.required) field.required = true; else delete field.required
    if (draft.sensitive) field.sensitive = true; else delete field.sensitive
    const defaultValue = params[draft.param]
    if (draft.sensitive) delete field.default
    else if (defaultValue !== undefined) field.default = defaultValue
    if (draft.type === 'enum') {
      const options = parseSettingOptions(draft.optionsText)
      if (!options.length) throw new Error(`枚举设置“${draft.label}”至少需要一个选项。`)
      if (!options.some((option) => Object.is(option.value, defaultValue))) {
        throw new Error(`枚举设置“${draft.label}”的当前参数值必须出现在选项中。`)
      }
      field.options = options
    } else {
      delete field.options
    }
    nextFields.push(field)
    nextBindings.push({
      setting_id: draft.id,
      target: { kind: 'process_param', node_id: nodeId, param: draft.param },
    })
    ids.add(draft.id)
  }

  return {
    settings_contract: JSON.stringify({ schema: SETTINGS_SCHEMA, storage_scope: 'cartridge', fields: nextFields }, null, 2),
    settings_bindings: JSON.stringify({ schema: BINDINGS_SCHEMA, bindings: nextBindings }, null, 2),
    ui_contract: typeof files.ui_contract === 'string' && files.ui_contract.trim()
      ? files.ui_contract
      : JSON.stringify({ schema: UI_SCHEMA, mode: 'none', host_capabilities: [] }, null, 2),
  }
}
