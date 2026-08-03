import { useEffect, useMemo, useState } from 'react'
import { Check, ChevronDown, CircleAlert, CircleCheck, Download, Eye, EyeOff, Hand, LoaderCircle, PackageOpen, Play, RefreshCw, RotateCcw, Save, Settings2, SlidersHorizontal } from 'lucide-react'
import type { FlowNode, NodeExperience, NodeExperienceControl, NodeExperienceInteractionMode, NodeExperienceMaterialVisibility } from '../../api.ts'
import type { NodeDraft } from './types.ts'
import { experienceParameterCandidates, nodeExperienceIssues, updateExperienceSection } from './nodeExperience.ts'

type PreviewState = 'waiting' | 'running' | 'action' | 'success' | 'error'

const PREVIEW_STATES: Array<{ id: PreviewState; label: string }> = [
  { id: 'waiting', label: '等待' },
  { id: 'running', label: '进行中' },
  { id: 'action', label: '需操作' },
  { id: 'success', label: '完成' },
  { id: 'error', label: '失败' },
]

const INTERACTION_MODES: Array<{ id: NodeExperienceInteractionMode; label: string }> = [
  { id: 'automatic', label: '自动执行' },
  { id: 'input', label: '填写内容' },
  { id: 'review', label: '确认审核' },
  { id: 'choice', label: '选择分支' },
]

const MATERIAL_VISIBILITY: Array<{ id: NodeExperienceMaterialVisibility; label: string }> = [
  { id: 'none', label: '不向用户展示' },
  { id: 'output', label: '只展示本步产出' },
  { id: 'input_output', label: '展示输入和产出' },
]

function splitFields(value: string) {
  return [...new Set(value.split(/[，,\n]/).map((item) => item.trim()).filter(Boolean))]
}

function EditorField({ label, value, onChange, multiline = false, placeholder = '' }: {
  label: string
  value: string
  onChange: (value: string) => void
  multiline?: boolean
  placeholder?: string
}) {
  return <label className={multiline ? 'wide' : undefined}><span>{label}</span>{multiline
    ? <textarea value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />
    : <input value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} />}</label>
}

function OptionalNumberField({ label, value, onChange }: { label: string; value: number | null; onChange: (value: number | null) => void }) {
  return <label><span>{label}</span><input type="number" value={value ?? ''} onChange={(event) => onChange(event.target.value === '' ? null : Number(event.target.value))} /></label>
}

function Toggle({ checked, label, help, onChange }: { checked: boolean; label: string; help?: string; onChange: (checked: boolean) => void }) {
  return <label className="cf-experience-toggle"><input type="checkbox" checked={checked} onChange={(event) => onChange(event.target.checked)} /><i /><span><strong>{label}</strong>{help && <small>{help}</small>}</span></label>
}

function PreviewStatus({ state, experience }: { state: PreviewState; experience: NodeExperience }) {
  if (state === 'waiting') return <div className="cf-consumer-preview-status waiting"><span><Play aria-hidden="true" /></span><div><strong>{experience.stage.waiting}</strong><small>前序步骤完成后自动开始</small></div></div>
  if (state === 'running') return <div className="cf-consumer-preview-status running"><span><LoaderCircle aria-hidden="true" /></span><div><strong>{experience.stage.running}</strong><small>{experience.materials.live_updates ? '物料会在这里实时更新' : '无需用户操作'}</small></div></div>
  if (state === 'success') return <div className="cf-consumer-preview-status success"><span><CircleCheck aria-hidden="true" /></span><div><strong>{experience.outcome.success_title}</strong><small>{experience.stage.success}</small></div></div>
  if (state === 'error') return <div className="cf-consumer-preview-status error"><span><CircleAlert aria-hidden="true" /></span><div><strong>{experience.outcome.error_title}</strong><small>{experience.outcome.error_message}</small></div></div>
  return <div className="cf-consumer-preview-status action"><span><Hand aria-hidden="true" /></span><div><strong>需要你的操作</strong><small>{experience.interaction.prompt || '此步骤没有要求用户处理的内容'}</small></div></div>
}

function ConsumerPreview({ node, experience }: { node: FlowNode; experience: NodeExperience }) {
  const [state, setState] = useState<PreviewState>('running')
  useEffect(() => { setState(experience.interaction.mode === 'automatic' ? 'running' : 'action') }, [node.id, experience.interaction.mode])
  const actions = Object.entries(experience.interaction.action_labels)
  const previewActions = actions.length ? actions : [['primary', experience.interaction.mode === 'input' ? '提交' : experience.interaction.mode === 'review' ? '确认' : '继续']]
  return <section className="cf-consumer-preview" aria-label="普通用户节点预览">
    <header><div><span>普通用户预览</span><strong>{experience.stage.label || node.title}</strong></div><i>{experience.visible ? <><Eye aria-hidden="true" />用户可见</> : <><EyeOff aria-hidden="true" />后台步骤</>}</i></header>
    <nav aria-label="预览状态">{PREVIEW_STATES.map((item) => <button type="button" key={item.id} className={state === item.id ? 'active' : ''} onClick={() => setState(item.id)}>{item.label}</button>)}</nav>
    {!experience.visible ? <div className="cf-consumer-preview-hidden"><EyeOff aria-hidden="true" /><strong>普通用户不会看到此步骤</strong><span>节点仍按配方执行，运行物料和诊断信息只在开发者台保留。</span></div> : <div className="cf-consumer-preview-screen">
      <p>{experience.stage.description}</p>
      <PreviewStatus state={state} experience={experience} />
      {state === 'action' && experience.interaction.mode === 'input' && experience.interaction.fields.length > 0 && <div className="cf-consumer-preview-fields">{experience.interaction.fields.map((field) => <label key={field.field}><span>{field.label}{field.required && <b>必填</b>}</span>{field.control === 'select' ? <select value="" disabled><option value="">{field.placeholder || '请选择'}</option>{field.options.map((option) => <option key={option}>{option}</option>)}</select> : field.control === 'textarea' ? <textarea value="" readOnly placeholder={field.placeholder} /> : <input type={field.control === 'date' ? 'date' : field.control === 'number' ? 'number' : field.control === 'toggle' ? 'checkbox' : 'text'} value={field.control === 'toggle' ? undefined : ''} readOnly placeholder={field.placeholder} />}{field.help && <small>{field.help}</small>}</label>)}</div>}
      {state === 'action' && experience.interaction.mode !== 'automatic' && <div className="cf-consumer-preview-actions">{previewActions.map(([id, label], index) => <button type="button" className={index === 0 ? 'primary' : ''} key={id}>{label}</button>)}</div>}
      {state === 'action' && experience.interaction.mode === 'automatic' && <div className="cf-consumer-preview-passive"><Check aria-hidden="true" />此步骤自动执行，不打断用户</div>}
      {(state === 'running' || state === 'success') && experience.materials.visibility !== 'none' && <div className="cf-consumer-preview-material"><PackageOpen aria-hidden="true" /><div><strong>{state === 'success' ? experience.outcome.result_label : experience.materials.label}</strong><span>{state === 'success' ? '结果预览会显示在这里' : experience.materials.live_updates ? '正在接收最新物料' : '完成后展示'}</span></div>{experience.materials.allow_download && <Download aria-hidden="true" />}</div>}
      {state === 'error' && experience.interaction.allow_retry && <div className="cf-consumer-preview-actions"><button type="button" className="primary"><RefreshCw aria-hidden="true" />{experience.outcome.retry_label}</button>{experience.interaction.allow_cancel && <button type="button">取消</button>}</div>}
    </div>}
  </section>
}

function ExperienceEditor({ node, experience, onChange }: { node: FlowNode; experience: NodeExperience; onChange: (experience: NodeExperience) => void }) {
  const candidates = useMemo(() => experienceParameterCandidates(node, experience), [experience, node])
  const controls = useMemo(() => {
    const byParameter = new Map<string, NodeExperienceControl>()
    for (const item of [...experience.controls, ...candidates]) if (!byParameter.has(item.parameter)) byParameter.set(item.parameter, item)
    return [...byParameter.values()]
  }, [candidates, experience.controls])
  const selectedControls = new Set(experience.controls.map((item) => item.parameter))
  const setStage = (patch: Partial<NodeExperience['stage']>) => onChange(updateExperienceSection(experience, 'stage', patch))
  const setInteraction = (patch: Partial<NodeExperience['interaction']>) => onChange(updateExperienceSection(experience, 'interaction', patch))
  const setMaterials = (patch: Partial<NodeExperience['materials']>) => onChange(updateExperienceSection(experience, 'materials', patch))
  const setOutcome = (patch: Partial<NodeExperience['outcome']>) => onChange(updateExperienceSection(experience, 'outcome', patch))
  const updateControl = (parameter: string, patch: Partial<NodeExperienceControl>) => onChange({ ...experience, controls: experience.controls.map((item) => item.parameter === parameter ? { ...item, ...patch } : item) })
  const updateInputField = (fieldId: string, patch: Partial<NodeExperience['interaction']['fields'][number]>) => setInteraction({ fields: experience.interaction.fields.map((field) => field.field === fieldId ? { ...field, ...patch } : field) })
  return <section className="cf-experience-editor">
    <details open>
      <summary><span><Eye aria-hidden="true" /><strong>用户呈现</strong><small>这个步骤是否出现，以及用户看到的进度</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="cf-experience-editor-body">
        <Toggle checked={experience.visible} label="在普通界面显示此步骤" help="关闭后仍会执行，但用户只看到前后可见阶段。" onChange={(visible) => onChange({ ...experience, visible })} />
        <div className="cf-experience-form-grid">
          <EditorField label="阶段名称" value={experience.stage.label} onChange={(label) => setStage({ label })} />
          <EditorField label="阶段说明" value={experience.stage.description} multiline onChange={(description) => setStage({ description })} />
          <EditorField label="等待时" value={experience.stage.waiting} onChange={(waiting) => setStage({ waiting })} />
          <EditorField label="进行中" value={experience.stage.running} onChange={(running) => setStage({ running })} />
          <EditorField label="完成时" value={experience.stage.success} onChange={(success) => setStage({ success })} />
        </div>
      </div>
    </details>

    <details>
      <summary><span><Hand aria-hidden="true" /><strong>用户操作</strong><small>普通用户在此处能做什么</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="cf-experience-editor-body">
        <label className="cf-experience-select"><span>操作方式</span><select value={experience.interaction.mode} onChange={(event) => setInteraction({ mode: event.target.value as NodeExperienceInteractionMode })}>{INTERACTION_MODES.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        {experience.interaction.mode !== 'automatic' && <div className="cf-experience-form-grid"><EditorField label="操作说明" value={experience.interaction.prompt} multiline onChange={(prompt) => setInteraction({ prompt })} /></div>}
        {experience.interaction.mode === 'input' && <div className="cf-experience-input-fields"><strong>输入字段呈现</strong>{experience.interaction.fields.length ? experience.interaction.fields.map((field) => <div key={field.field}><header><code>{field.field}</code><Toggle checked={field.required} label="必填" onChange={(required) => updateInputField(field.field, { required })} /></header><div className="cf-experience-control-fields"><EditorField label="用户名称" value={field.label} onChange={(label) => updateInputField(field.field, { label })} /><EditorField label="占位提示" value={field.placeholder} onChange={(placeholder) => updateInputField(field.field, { placeholder })} /><EditorField label="帮助说明" value={field.help} onChange={(help) => updateInputField(field.field, { help })} /><label className="cf-experience-select"><span>控件</span><select value={field.control} onChange={(event) => updateInputField(field.field, { control: event.target.value as typeof field.control })}><option value="text">单行文本</option><option value="textarea">多行文本</option><option value="number">数字输入</option><option value="date">日期</option><option value="select">选项</option><option value="toggle">开关</option></select></label>{field.control === 'select' && <EditorField label="选项（逗号分隔）" value={field.options.join('，')} onChange={(value) => updateInputField(field.field, { options: splitFields(value) })} />}</div></div>) : <p>节点输入契约中没有可呈现的字段，需要先由 AI 补齐输入轮廓。</p>}</div>}
        {experience.interaction.mode !== 'automatic' && <div className="cf-experience-action-labels"><strong>按钮与结果</strong>{Object.entries(experience.interaction.action_labels).length ? Object.entries(experience.interaction.action_labels).map(([actionId, label]) => <label key={actionId}><code>{actionId}</code><input value={label} onChange={(event) => setInteraction({ action_labels: { ...experience.interaction.action_labels, [actionId]: event.target.value } })} /></label>) : <p>当前节点没有命名分支，普通界面使用默认确认按钮。</p>}</div>}
        <div className="cf-experience-toggle-row"><Toggle checked={experience.interaction.allow_retry} label="允许重试" onChange={(allow_retry) => setInteraction({ allow_retry })} /><Toggle checked={experience.interaction.allow_cancel} label="允许取消" onChange={(allow_cancel) => setInteraction({ allow_cancel })} /></div>
      </div>
    </details>

    <details>
      <summary><span><PackageOpen aria-hidden="true" /><strong>运行物料</strong><small>用户可以实时看到哪些输入和产出</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="cf-experience-editor-body">
        <label className="cf-experience-select"><span>展示范围</span><select value={experience.materials.visibility} onChange={(event) => setMaterials({ visibility: event.target.value as NodeExperienceMaterialVisibility })}>{MATERIAL_VISIBILITY.map((item) => <option value={item.id} key={item.id}>{item.label}</option>)}</select></label>
        {experience.materials.visibility !== 'none' && <div className="cf-experience-form-grid"><EditorField label="物料名称" value={experience.materials.label} onChange={(label) => setMaterials({ label })} /><EditorField label="隐藏字段" value={experience.materials.hidden_fields.join('，')} placeholder="内部 ID，诊断信息" onChange={(value) => setMaterials({ hidden_fields: splitFields(value) })} /></div>}
        <div className="cf-experience-toggle-row"><Toggle checked={experience.materials.live_updates} label="实时更新" onChange={(live_updates) => setMaterials({ live_updates })} /><Toggle checked={experience.materials.allow_download} label="允许下载" onChange={(allow_download) => setMaterials({ allow_download })} /></div>
      </div>
    </details>

    <details>
      <summary><span><CircleCheck aria-hidden="true" /><strong>结果与失败</strong><small>完成后的交付和出错后的恢复</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="cf-experience-editor-body"><div className="cf-experience-form-grid">
        <EditorField label="成功标题" value={experience.outcome.success_title} onChange={(success_title) => setOutcome({ success_title })} />
        <EditorField label="结果名称" value={experience.outcome.result_label} onChange={(result_label) => setOutcome({ result_label })} />
        <EditorField label="空结果说明" value={experience.outcome.empty_text} onChange={(empty_text) => setOutcome({ empty_text })} />
        <EditorField label="失败标题" value={experience.outcome.error_title} onChange={(error_title) => setOutcome({ error_title })} />
        <EditorField label="失败说明" value={experience.outcome.error_message} multiline onChange={(error_message) => setOutcome({ error_message })} />
        <EditorField label="重试按钮" value={experience.outcome.retry_label} onChange={(retry_label) => setOutcome({ retry_label })} />
      </div><Toggle checked={experience.outcome.preserve_partial} label="失败时保留已完成物料" onChange={(preserve_partial) => setOutcome({ preserve_partial })} /></div>
    </details>

    <details>
      <summary><span><SlidersHorizontal aria-hidden="true" /><strong>开放参数</strong><small>只把明确允许的关键参数交给普通用户</small></span><ChevronDown aria-hidden="true" /></summary>
      <div className="cf-experience-editor-body cf-experience-controls">{controls.length ? controls.map((control) => {
        const selected = selectedControls.has(control.parameter)
        return <div className={selected ? 'selected' : ''} key={control.parameter}>
          <Toggle checked={selected} label={control.label || control.parameter} help={control.parameter} onChange={(checked) => onChange({ ...experience, controls: checked ? [...experience.controls, control] : experience.controls.filter((item) => item.parameter !== control.parameter) })} />
          {selected && <div className="cf-experience-control-fields"><EditorField label="用户名称" value={control.label} onChange={(label) => updateControl(control.parameter, { label })} /><EditorField label="帮助说明" value={control.help} onChange={(help) => updateControl(control.parameter, { help })} /><label className="cf-experience-select"><span>控件</span><select value={control.control} onChange={(event) => updateControl(control.parameter, { control: event.target.value as NodeExperienceControl['control'] })}><option value="text">文本框</option><option value="number">数字输入</option><option value="slider">滑杆</option><option value="select">选项</option><option value="toggle">开关</option></select></label>{control.control === 'select' && <EditorField label="选项（逗号分隔）" value={control.options.join('，')} onChange={(value) => updateControl(control.parameter, { options: splitFields(value) })} />}{(control.control === 'number' || control.control === 'slider') && <div className="cf-experience-number-range"><OptionalNumberField label="最小值" value={control.minimum} onChange={(minimum) => updateControl(control.parameter, { minimum })} /><OptionalNumberField label="最大值" value={control.maximum} onChange={(maximum) => updateControl(control.parameter, { maximum })} /><OptionalNumberField label="步长" value={control.step} onChange={(step) => updateControl(control.parameter, { step })} /></div>}<Toggle checked={control.required} label="必填" onChange={(required) => updateControl(control.parameter, { required })} /></div>}
        </div>
      }) : <p className="cf-experience-empty">该节点没有适合向普通用户开放的安全参数。Prompt、工具、路径和凭据不会出现在这里。</p>}</div>
    </details>
  </section>
}

export function NodeExperiencePanel({ node, draft, editing, versioned, dirty = false, saving = false, onDraftChange, onReset, onSave }: {
  node: FlowNode
  draft: NodeDraft
  editing: boolean
  versioned: boolean
  dirty?: boolean
  saving?: boolean
  onDraftChange?: (patch: Partial<NodeDraft>) => void
  onReset?: () => void
  onSave?: () => void
}) {
  const experience = draft.experience
  const issues = nodeExperienceIssues(node, experience)
  return <section className="cf-node-experience-panel">
    <div className="cf-experience-summary"><div><strong>普通用户体验</strong><span>{versioned ? '这里的设置随配方版本发布，普通用户不会看到节点工程详情。' : '当前卡带会直接保存此设置；升级到 CF-FARP@1.1 后纳入配方版本。'}</span></div><i className={issues.length ? 'needs-work' : 'ready'}>{issues.length ? `${issues.length} 项待确认` : versioned ? '可以发布' : '已配置'}</i></div>
    <ConsumerPreview node={node} experience={experience} />
    {issues.length > 0 && <section className="cf-experience-readiness"><header><CircleAlert aria-hidden="true" /><strong>体验检查</strong><span>{issues.length}</span></header><ul>{issues.map((issue) => <li key={issue.code}><code>{issue.code}</code><span>{issue.message}</span></li>)}</ul></section>}
    {editing && onDraftChange ? <ExperienceEditor node={node} experience={experience} onChange={(next) => onDraftChange({ experience: next })} /> : <div className="cf-experience-readonly"><Settings2 aria-hidden="true" /><span>点击右上角“编辑”，调整普通用户在此步骤看到和能够操作的内容。</span></div>}
    {editing && <footer className="cf-experience-savebar"><span>{dirty ? versioned ? '修改仅存在于调优草稿' : '修改尚未保存' : '当前节点配置已保存'}</span><button type="button" disabled={!dirty || saving} onClick={onReset}><RotateCcw aria-hidden="true" />重置</button><button type="button" className="primary" disabled={!dirty || saving} onClick={onSave}><Save aria-hidden="true" />{saving ? '保存中...' : '保存节点配置'}</button></footer>}
  </section>
}
