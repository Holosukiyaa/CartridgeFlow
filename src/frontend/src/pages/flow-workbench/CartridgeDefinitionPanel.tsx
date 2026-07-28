import { useEffect, useMemo, useState } from 'react'
import { Save } from 'lucide-react'
import { saveLabFlowFile, type FlowFiles } from '../../api.ts'
import { showToast } from '../../toast.tsx'

type DefinitionKey = 'inputs' | 'roles' | 'tools' | 'outputs'

const labels: Record<DefinitionKey, { title: string; hint: string }> = {
  inputs: { title: '运行入口', hint: 'manifest.inputs · 启动运行时收集的参数' },
  roles: { title: '模型角色', hint: 'manifest.llm_recipe.roles · 节点通过 role 引用' },
  tools: { title: '工具绑定', hint: 'manifest.mcp_tools · 节点通过 tool_binding 引用' },
  outputs: { title: '交付输出', hint: 'manifest.outputs · 对外声明的最终产物' },
}

function readManifest(files: FlowFiles) {
  try { return JSON.parse(files.manifest || '{}') as Record<string, any> } catch { return {} }
}

export function CartridgeDefinitionPanel({ flowId, files, onFilesChange, onManifestChange }: {
  flowId: string
  files: FlowFiles
  onFilesChange: (files: FlowFiles) => void
  onManifestChange?: (manifest: Record<string, any>) => void
}) {
  const manifest = useMemo(() => readManifest(files), [files.manifest])
  const [drafts, setDrafts] = useState<Record<DefinitionKey, string>>({ inputs: '[]', roles: '[]', tools: '[]', outputs: '[]' })
  const [openKey, setOpenKey] = useState<DefinitionKey>('inputs')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    setDrafts({
      inputs: JSON.stringify(manifest.inputs || [], null, 2),
      roles: JSON.stringify(manifest.llm_recipe?.roles || [], null, 2),
      tools: JSON.stringify(manifest.mcp_tools || [], null, 2),
      outputs: JSON.stringify(manifest.outputs || [], null, 2),
    })
  }, [manifest])

  const counts = {
    inputs: Array.isArray(manifest.inputs) ? manifest.inputs.length : 0,
    roles: Array.isArray(manifest.llm_recipe?.roles) ? manifest.llm_recipe.roles.length : 0,
    tools: Array.isArray(manifest.mcp_tools) ? manifest.mcp_tools.length : 0,
    outputs: Array.isArray(manifest.outputs) ? manifest.outputs.length : 0,
  }

  const save = async () => {
    try {
      const parsed = Object.fromEntries((Object.keys(labels) as DefinitionKey[]).map((key) => {
        const value = JSON.parse(drafts[key] || '[]')
        if (!Array.isArray(value)) throw new Error(`${labels[key].title}必须是 JSON 数组`)
        return [key, value]
      })) as Record<DefinitionKey, any[]>
      const nextManifest = {
        ...manifest,
        inputs: parsed.inputs,
        outputs: parsed.outputs,
        mcp_tools: parsed.tools,
        ...(parsed.roles.length || manifest.llm_recipe ? {
          llm_recipe: {
            schema: 'cartridgeflow.llm_recipe.v1',
            ...(manifest.llm_recipe || {}),
            roles: parsed.roles,
          },
        } : {}),
      }
      setBusy(true)
      const content = `${JSON.stringify(nextManifest, null, 2)}\n`
      await saveLabFlowFile(flowId, 'manifest', content)
      onFilesChange({ ...files, manifest: content })
      onManifestChange?.(nextManifest)
      showToast({ title: '卡带运行定义已保存', type: 'success' })
    } catch (error: any) {
      showToast({ title: '卡带运行定义保存失败', description: error.message || String(error), type: 'error' })
    } finally {
      setBusy(false)
    }
  }

  return <section className="cf-cartridge-definition">
    <header><div><strong>卡带运行定义</strong><small>这里是手工开发闭环的清单入口</small></div></header>
    <nav aria-label="卡带运行定义分区">
      {(Object.keys(labels) as DefinitionKey[]).map((key) => <button type="button" key={key} className={openKey === key ? 'active' : ''} onClick={() => setOpenKey(key)}><span>{labels[key].title}</span><b>{counts[key]}</b></button>)}
    </nav>
    <label className="cf-cartridge-definition-editor">
      <span>{labels[openKey].title}</span>
      <small>{labels[openKey].hint}</small>
      <textarea spellCheck={false} value={drafts[openKey]} onChange={(event) => setDrafts((current) => ({ ...current, [openKey]: event.target.value }))} />
    </label>
    <button type="button" className="cf-cartridge-definition-save" disabled={busy} onClick={() => void save()}><Save />{busy ? '保存中...' : '保存运行定义'}</button>
  </section>
}
