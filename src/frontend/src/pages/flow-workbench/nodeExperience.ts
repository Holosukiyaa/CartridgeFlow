import type { FlowNode, NodeExperience, NodeExperienceControl, NodeExperienceInputField, NodeExperienceInteractionMode } from '../../api.ts'

export type NodeExperienceIssue = {
  code: string
  message: string
  section: 'stage' | 'interaction' | 'materials' | 'outcome' | 'controls'
}

const HIDDEN_PARAMETER_KEYS = /(?:prompt|system|input|output|save|path|token|secret|password|key|credential|authorization|cookie|script|code|command|tool|model|role|endpoint)/i

function text(value: unknown) {
  return typeof value === 'string' ? value.trim() : ''
}

function humanize(value: string) {
  const normalized = value.replace(/[_-]+/g, ' ').trim()
  if (!normalized) return ''
  const known: Record<string, string> = {
    approve: '通过', reject: '退回', revise: '修改', retry: '重试', continue: '继续', cancel: '取消',
    confirm: '确认', submit: '提交', yes: '是', no: '否', temperature: '创意程度', max_tokens: '最大输出', timeout_ms: '等待时间',
    edition_date: '日报日期', focus_topics: '关注主题', topic: '主题', style: '风格', target_audience: '目标读者',
    scene_theme: '场景主题', movement_style: '操作偏好', feedback: '修改意见',
  }
  return known[value.toLowerCase()] || normalized
}

function inferInteractionMode(node: FlowNode): NodeExperienceInteractionMode {
  const declared = text(node.interaction_mode).toLowerCase()
  if (declared === 'collect') return 'input'
  if (declared === 'review') return 'review'
  if (Object.keys(node.action_routes || {}).length > 1) return 'choice'
  if (node.kind === 'interaction' || node.executor === 'user' || node.executor === 'human') return 'review'
  return 'automatic'
}

function defaultActionLabels(node: FlowNode, mode: NodeExperienceInteractionMode) {
  const labels = Object.keys(node.action_routes || {}).reduce<Record<string, string>>((result, actionId) => {
    result[actionId] = humanize(actionId)
    return result
  }, {})
  if (!Object.keys(labels).length && mode !== 'automatic') {
    if (mode === 'review') {
      labels.approve = '通过并继续'
      labels.reject = '退回修改'
    } else {
      labels[mode === 'input' ? 'submit' : 'continue'] = mode === 'input' ? '提交' : '继续'
    }
  }
  return labels
}

function defaultMaterialLabel(node: FlowNode, stageLabel: string) {
  if (node.id === 'complete' || node.action === 'complete' || node.action === 'end') return '最终结果'
  return `${stageLabel}结果`
}

function defaultInputFields(node: FlowNode, mode: NodeExperienceInteractionMode): NodeExperienceInputField[] {
  if (mode !== 'input') return []
  const schema = node.input_schema && typeof node.input_schema === 'object' ? node.input_schema : {}
  const properties = schema.properties && typeof schema.properties === 'object' ? schema.properties : {}
  const declared = Array.isArray(node.params?.fields) ? node.params.fields.map(String) : []
  const fields = [...new Set([...declared, ...Object.keys(properties)])]
  const required = new Set(Array.isArray(schema.required) ? schema.required.map(String) : declared)
  return fields.map((field) => {
    const definition = properties[field] && typeof properties[field] === 'object' ? properties[field] : {}
    const enumOptions = Array.isArray(definition.enum) ? definition.enum.map(String) : []
    const control = text(definition.format) === 'date' || /date/i.test(field)
      ? 'date'
      : enumOptions.length
        ? 'select'
        : definition.type === 'number' || definition.type === 'integer'
          ? 'number'
          : definition.type === 'boolean'
            ? 'toggle'
            : /topic|style|description|feedback|content/i.test(field)
              ? 'textarea'
              : 'text'
    return {
      field,
      label: text(definition.title) || humanize(field),
      help: text(definition.description),
      placeholder: text(definition.placeholder),
      control,
      required: required.has(field),
      options: enumOptions,
    } satisfies NodeExperienceInputField
  })
}

export function createDefaultNodeExperience(node: FlowNode): NodeExperience {
  const label = text(node.display_name) || text(node.title) || node.id
  const description = text(node.description) || text(node.params?.description) || text(node.params?.message)
  const interactionMode = inferInteractionMode(node)
  const hasOutput = Object.keys(node.outputs || {}).length > 0 || Boolean(node.params?.output || node.params?.save_to)
  const isStart = node.id === 'start' || node.action === 'start'
  const isComplete = node.id === 'complete' || node.action === 'complete' || node.action === 'end'
  const materialLabel = defaultMaterialLabel(node, label)
  return {
    schema: 'cartridgeflow.node_experience.v1',
    visible: !isStart,
    stage: {
      label,
      description: description || (isComplete ? '全部处理已经完成。' : `系统将完成“${label}”。`),
      waiting: `等待开始${label}`,
      running: `正在${label}`,
      success: isComplete ? '全部完成' : `${label}已完成`,
    },
    interaction: {
      mode: interactionMode,
      prompt: interactionMode === 'automatic' ? '' : text(node.params?.interaction?.prompt) || text(node.params?.prompt) || text(node.params?.message) || `请确认“${label}”的处理结果。`,
      action_labels: defaultActionLabels(node, interactionMode),
      fields: defaultInputFields(node, interactionMode),
      allow_retry: !isComplete,
      allow_cancel: !isComplete,
    },
    materials: {
      visibility: hasOutput ? 'output' : 'none',
      label: materialLabel,
      live_updates: hasOutput && !isComplete,
      allow_download: Boolean(node.params?.artifact_type || node.params?.delivery_path || node.params?.save_to),
      hidden_fields: [],
    },
    outcome: {
      success_title: isComplete ? '处理完成' : `${label}完成`,
      result_label: materialLabel,
      empty_text: '暂时没有可展示的结果',
      error_title: `${label}未完成`,
      error_message: '本步骤暂时无法完成，已完成的内容不会丢失。',
      retry_label: '重试本步骤',
      preserve_partial: true,
    },
    controls: [],
  }
}

export function normalizeNodeExperience(node: FlowNode): NodeExperience {
  const fallback = createDefaultNodeExperience(node)
  const source = node.experience
  if (!source || typeof source !== 'object') return fallback
  return {
    ...fallback,
    ...source,
    schema: 'cartridgeflow.node_experience.v1',
    stage: { ...fallback.stage, ...(source.stage || {}) },
    interaction: {
      ...fallback.interaction,
      ...(source.interaction || {}),
      action_labels: { ...fallback.interaction.action_labels, ...(source.interaction?.action_labels || {}) },
      fields: Array.isArray(source.interaction?.fields)
        ? source.interaction.fields.map((field) => ({ ...field, options: Array.isArray(field.options) ? field.options : [] }))
        : fallback.interaction.fields,
    },
    materials: { ...fallback.materials, ...(source.materials || {}) },
    outcome: { ...fallback.outcome, ...(source.outcome || {}) },
    controls: Array.isArray(source.controls)
      ? source.controls.map((control) => ({
        ...control,
        options: Array.isArray(control.options) ? control.options : [],
        minimum: control.minimum ?? null,
        maximum: control.maximum ?? null,
        step: control.step ?? null,
      }))
      : [],
  }
}

export function nodeExperienceIssues(node: FlowNode, experience = normalizeNodeExperience(node)): NodeExperienceIssue[] {
  const issues: NodeExperienceIssue[] = []
  if (!node.experience) issues.push({ code: 'EXPERIENCE_NOT_SAVED', message: '当前使用系统生成的安全默认值，发布前应确认并保存。', section: 'stage' })
  if (experience.visible && !text(experience.stage.label)) issues.push({ code: 'STAGE_LABEL_MISSING', message: '普通用户看不到这个阶段的名称。', section: 'stage' })
  if (experience.visible && !text(experience.stage.running)) issues.push({ code: 'RUNNING_COPY_MISSING', message: '运行时没有可展示的进度文案。', section: 'stage' })
  if (experience.interaction.mode !== 'automatic' && !text(experience.interaction.prompt)) issues.push({ code: 'INTERACTION_PROMPT_MISSING', message: '需要用户操作，但没有说明用户要做什么。', section: 'interaction' })
  if (experience.interaction.mode === 'input' && !experience.interaction.fields.length) issues.push({ code: 'INPUT_FIELDS_MISSING', message: '需要用户填写内容，但没有定义任何用户字段。', section: 'interaction' })
  if (experience.interaction.fields.some((field) => !text(field.label))) issues.push({ code: 'INPUT_FIELD_LABEL_MISSING', message: '至少一个输入字段没有面向用户的名称。', section: 'interaction' })
  if (experience.interaction.mode !== 'automatic' && Object.keys(node.action_routes || {}).some((key) => !text(experience.interaction.action_labels[key]))) {
    issues.push({ code: 'ACTION_LABEL_MISSING', message: '至少一个操作结果没有面向用户的按钮名称。', section: 'interaction' })
  }
  if (experience.materials.visibility !== 'none' && !text(experience.materials.label)) issues.push({ code: 'MATERIAL_LABEL_MISSING', message: '运行物料缺少用户能理解的名称。', section: 'materials' })
  if (!text(experience.outcome.error_message) || (experience.interaction.allow_retry && !text(experience.outcome.retry_label))) {
    issues.push({ code: 'RECOVERY_COPY_MISSING', message: '失败后没有完整说明或恢复操作。', section: 'outcome' })
  }
  return issues
}

export function experienceParameterCandidates(node: FlowNode, experience: NodeExperience): NodeExperienceControl[] {
  const existing = new Map(experience.controls.map((control) => [control.parameter, control]))
  return Object.entries(node.params || {})
    .filter(([key, value]) => !HIDDEN_PARAMETER_KEYS.test(key) && ['string', 'number', 'boolean'].includes(typeof value))
    .map(([parameter, value]) => existing.get(parameter) || {
      parameter,
      label: humanize(parameter),
      help: '允许普通用户在运行前调整此参数。',
      control: typeof value === 'boolean' ? 'toggle' : typeof value === 'number' ? 'number' : 'text',
      required: false,
      options: [],
      minimum: parameter === 'temperature' ? 0 : null,
      maximum: parameter === 'temperature' ? 2 : null,
      step: typeof value === 'number' ? parameter === 'temperature' ? 0.1 : 1 : null,
    })
}

export function updateExperienceSection<K extends keyof Pick<NodeExperience, 'stage' | 'interaction' | 'materials' | 'outcome'>>(
  experience: NodeExperience,
  section: K,
  patch: Partial<NodeExperience[K]>,
): NodeExperience {
  return { ...experience, [section]: { ...experience[section], ...patch } }
}
