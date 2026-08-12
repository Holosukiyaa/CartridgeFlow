import { type AnyRecord } from './model'

export type DisplayFieldType = 'text' | 'number' | 'boolean' | 'list'
export type PreviewState = 'normal' | 'long' | 'empty'
export type DisplayFieldDraft = {
  id: string
  label: string
  type: DisplayFieldType
  required: boolean
  source: string
}

export type DisplaySource = { value: string; label: string }

const object = (value: unknown) => value && typeof value === 'object' && !Array.isArray(value) ? value as AnyRecord : {}
const array = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []

export function componentSlug(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9._-]+/g, '.').replace(/^[._-]+|[._-]+$/g, '').slice(0, 80)
}

export function nextComponentId(ids: string[], base = 'result.panel'): string {
  const used = new Set(ids)
  let candidate = base
  for (let index = 2; used.has(candidate); index += 1) candidate = `${base}.${index}`
  return candidate
}

export function displaySources(graph: AnyRecord, manifestInputs: AnyRecord[]): DisplaySource[] {
  const sources = new Map<string, string>([
    ['store:result', '通用结果'],
    ['store:summary', '结果摘要'],
    ['store:items', '结果列表'],
  ])
  manifestInputs.forEach((input) => {
    const id = String(input.id || '').trim()
    if (id) sources.set(`store:${id}`, String(input.label || input.name || id))
  })
  array(graph.nodes).forEach((node) => {
    const nodeLabel = String(node.display_name || node.title || node.id)
    Object.entries(object(node.outputs)).forEach(([outputId, raw]) => {
      const output = object(raw)
      const target = object(output.target)
      const targetId = String(target.key || target.artifact_id || '').trim()
      if (targetId && target.type === 'store') {
        sources.set(`store:${targetId}`, `${nodeLabel} / ${String(object(output.schema).title || outputId)}`)
      }
    })
  })
  return [...sources].map(([value, label]) => ({ value, label }))
}

export function generatedComponentDraft(component: AnyRecord): { templateId: string; fields: DisplayFieldDraft[] } | null {
  const authoring = object(component.authoring)
  if (authoring.kind !== 'passive_display_v1') return null
  const fields = array(authoring.fields).map((field) => ({
    id: String(field.id || ''),
    label: String(field.label || ''),
    type: (['text', 'number', 'boolean', 'list'].includes(String(field.type)) ? String(field.type) : 'text') as DisplayFieldType,
    required: Boolean(field.required),
    source: String(field.source || ''),
  }))
  return { templateId: String(authoring.template_id || 'summary'), fields }
}

export function mockDisplayValue(field: DisplayFieldDraft, state: PreviewState): unknown {
  if (state === 'empty') return field.type === 'list' ? [] : null
  if (field.type === 'number') return state === 'long' ? 128930 : 128
  if (field.type === 'boolean') return state === 'normal'
  if (field.type === 'list') {
    return state === 'long'
      ? ['已汇总全部运行资料并完成来源核对', '发现三个值得继续跟进的关键变化', '下一步建议先处理高优先级异常再发布结果']
      : ['完成资料汇总', '生成交付结果', '记录运行证据']
  }
  return state === 'long'
    ? '本次运行已经完成，系统汇总了完整结果、关键变化和后续建议，并保留了能够追溯到原始来源的交付信息。'
    : '本次运行已完成。'
}
