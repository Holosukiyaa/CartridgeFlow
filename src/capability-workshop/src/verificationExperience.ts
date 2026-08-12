import { type AnyRecord } from './model'

const list = (value: unknown) => Array.isArray(value) ? value as AnyRecord[] : []

function sampleValue(input: AnyRecord): unknown {
  if (input.default !== undefined && input.default !== null && input.default !== '') return input.default
  const type = String(input.type || 'text')
  if (type === 'boolean' || type === 'checkbox') return true
  if (type === 'number' || type === 'integer') return 1
  if (type === 'array' || type === 'string_list') return ['验收条目']
  if (type === 'object') return { sample: '验收数据' }
  if (type === 'select') return list(input.options)[0]?.value ?? 'feature'
  return type === 'textarea' ? '用于真实运行验收的内容' : '验收输入'
}

export function buildVerificationCases(inputs: AnyRecord[]): {
  success: AnyRecord
  failure: AnyRecord
  failureField: AnyRecord | undefined
} {
  const success = Object.fromEntries(inputs.filter((input) => input.id).map((input) => [String(input.id), sampleValue(input)]))
  const failureField = inputs.find((input) => input.id && input.required === true)
  const failure = { ...success }
  if (failureField) {
    const type = String(failureField.type || 'text')
    failure[String(failureField.id)] = type === 'array' || type === 'string_list' ? [] : type === 'object' ? {} : null
  }
  return { success, failure, failureField }
}

export function updateVerificationInput(current: AnyRecord, input: AnyRecord, raw: string | boolean): AnyRecord {
  const type = String(input.type || 'text')
  let value: unknown = raw
  if (type === 'boolean' || type === 'checkbox') value = Boolean(raw)
  if (type === 'number' || type === 'integer') value = raw === '' ? null : Number(raw)
  if (type === 'array' || type === 'string_list') value = String(raw).split(/\r?\n/).map((item) => item.trim()).filter(Boolean)
  if (type === 'object') {
    try { value = JSON.parse(String(raw || '{}')) } catch { value = raw }
  }
  return { ...current, [String(input.id)]: value }
}

export function runDiagnosis(run: AnyRecord): { tone: 'idle' | 'running' | 'success' | 'failure'; title: string; detail: string } {
  const status = String(run.status || '')
  if (!status) return { tone: 'idle', title: '尚未运行', detail: '' }
  if (['created', 'queued', 'running', 'retrying'].includes(status)) return { tone: 'running', title: '正在运行', detail: String(run.run_id || '') }
  if (status === 'completed') return { tone: 'success', title: '成功路径完成', detail: String(run.run_id || '') }
  const error = run.error && typeof run.error === 'object' ? run.error as AnyRecord : {}
  const code = String(error.code || 'RUNTIME_FAILED')
  const owner = String(error.node_id || run.current_state || '运行时')
  const message = String(error.message || '运行没有完成。')
  return { tone: 'failure', title: `${code} · ${owner}`, detail: message }
}

export function isCurrentVerification(value: AnyRecord): boolean {
  return value.status === 'current' && Boolean((value.verification as AnyRecord | undefined)?.token)
}
