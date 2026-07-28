import { Plus, Trash2 } from 'lucide-react'
import type { FlowFiles, FlowNode, InteractionComponent } from '../../api.ts'

type ContractPatch = { inputBinding?: string; actionRoutes?: string }

function parseRecord(source: string) {
  try {
    const value = JSON.parse(source || '{}')
    return value && typeof value === 'object' && !Array.isArray(value)
      ? { valid: true as const, value: value as Record<string, string> }
      : { valid: false as const, value: {} }
  } catch {
    return { valid: false as const, value: {} }
  }
}

function readComponents(files: FlowFiles): InteractionComponent[] {
  try {
    const document = JSON.parse(files.interaction_components || '{}')
    return Array.isArray(document.components) ? document.components : []
  } catch {
    return []
  }
}

function outputNames(node: FlowNode) {
  const params = node.params || {}
  return [node.output, node.primary_output, params.output, params.save_to]
    .flatMap((value) => Array.isArray(value) ? value : String(value || '').split(/[,\n]/))
    .map((value) => String(value).trim())
    .filter(Boolean)
}

function writeRecord(value: Record<string, string>) {
  return JSON.stringify(value, null, 2)
}

export function InteractionContractEditor({ files, componentRef, currentNodeId, graphNodes, inputBinding, actionRoutes, showBindings = true, showRoutes = true, onChange }: {
  files: FlowFiles
  componentRef: string
  currentNodeId: string
  graphNodes: FlowNode[]
  inputBinding: string
  actionRoutes: string
  showBindings?: boolean
  showRoutes?: boolean
  onChange: (patch: ContractPatch) => void
}) {
  const bindingState = parseRecord(inputBinding)
  const routeState = parseRecord(actionRoutes)
  const component = readComponents(files).find((item) => item.id === componentRef)
  const componentActions = component?.actions || []
  const storeOptions = graphNodes.flatMap((node) => outputNames(node).map((name) => ({ value: `store:${name}`, label: `${node.display_name || node.title || node.id} · ${name}` })))
  const actionIds = new Set(componentActions.map((item) => item.id))
  const routeIds = [...componentActions.map((item) => item.id), ...Object.keys(routeState.value).filter((id) => !actionIds.has(id))]

  const replaceBinding = (oldName: string, name: string, reference: string) => {
    const next = Object.fromEntries(Object.entries(bindingState.value).filter(([key]) => key !== oldName))
    if (name.trim()) next[name.trim()] = reference
    onChange({ inputBinding: writeRecord(next) })
  }
  const removeBinding = (name: string) => {
    const next = { ...bindingState.value }
    delete next[name]
    onChange({ inputBinding: writeRecord(next) })
  }
  const addBinding = () => {
    let index = Object.keys(bindingState.value).length + 1
    while (`field_${index}` in bindingState.value) index += 1
    onChange({ inputBinding: writeRecord({ ...bindingState.value, [`field_${index}`]: storeOptions[0]?.value || 'store:' }) })
  }
  const setRoute = (actionId: string, target: string) => {
    const next = { ...routeState.value }
    if (target) next[actionId] = target
    else delete next[actionId]
    onChange({ actionRoutes: writeRecord(next) })
  }

  return <div className="cf-interaction-contract-editor">
    {showBindings && <section>
      <header><div><strong>输入字段映射</strong><small>组件字段读取受控 Store 或 Artifact</small></div>{bindingState.valid && <button type="button" onClick={addBinding}><Plus />添加</button>}</header>
      {bindingState.valid ? <div className="cf-contract-rows">
        {Object.entries(bindingState.value).map(([name, reference]) => <div className="cf-contract-row binding" key={name}>
          <input aria-label="组件字段" value={name} onChange={(event) => replaceBinding(name, event.target.value, reference)} placeholder="组件字段" />
          <span>←</span>
          <input aria-label={`${name}的数据来源`} list={`interaction-store-options-${currentNodeId}`} value={reference} onChange={(event) => replaceBinding(name, name, event.target.value)} placeholder="store:key 或 artifact:id" />
          <button type="button" onClick={() => removeBinding(name)} title="删除映射"><Trash2 /></button>
        </div>)}
        {!Object.keys(bindingState.value).length && <p>当前组件不读取运行数据。</p>}
        <datalist id={`interaction-store-options-${currentNodeId}`}>{storeOptions.map((option) => <option key={`${option.label}:${option.value}`} value={option.value}>{option.label}</option>)}</datalist>
      </div> : <label className="cf-contract-invalid"><span>当前 JSON 无法结构化，请先修正</span><textarea value={inputBinding} onChange={(event) => onChange({ inputBinding: event.target.value })} /></label>}
    </section>}

    {showRoutes && <section>
      <header><div><strong>命名动作路由</strong><small>Host 动作只能进入静态声明的目标节点</small></div></header>
      {routeState.valid ? <div className="cf-contract-rows">
        {routeIds.map((actionId) => {
          const action = componentActions.find((item) => item.id === actionId)
          return <label className="cf-contract-row route" key={actionId}>
            <span title={actionId}>{action?.label || actionId}</span>
            <code>{actionId}</code>
            <select value={routeState.value[actionId] || ''} onChange={(event) => setRoute(actionId, event.target.value)}>
              <option value="">不在本节点开放</option>
              {graphNodes.filter((node) => node.id !== currentNodeId).map((node) => <option key={node.id} value={node.id}>{node.display_name || node.title || node.id} · {node.id}</option>)}
            </select>
          </label>
        })}
        {!routeIds.length && <p>{componentRef ? '当前组件还没有声明命名动作。' : '先选择交互组件，再配置动作路由。'}</p>}
      </div> : <label className="cf-contract-invalid"><span>当前路由 JSON 无法结构化，请先修正</span><textarea value={actionRoutes} onChange={(event) => onChange({ actionRoutes: event.target.value })} /></label>}
    </section>}
  </div>
}
