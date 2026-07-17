import { useState } from 'react'
import { Badge, Box, Button, Field, Grid, HStack, Heading, TabsContent, TabsList, TabsRoot, TabsTrigger, Text, Textarea, VStack } from '../../ui.tsx'
import {
  applyStewardPatches,
  previewLabFlowGraph,
  saveLabFlowFile,
  suggestFlowChanges,
  validateLabFlow,
  type FlowFiles,
  type FlowLabDetail,
  type FlowNode,
  type StewardSuggestion,
  type ValidationResponse,
} from '../../api.ts'
import { showToast } from '../../toast.tsx'
import { FILE_TABS } from './nodeModel.ts'
import { Inspector, ValidationCard } from './cards.tsx'

export function AdvancedView({ flowId, detail, files, activeFile, selectedNode, validation, inspectorTitle, inspectorData, stewardPatches, onFilesChange, onActiveFileChange, onValidationChange, onInspectorChange, onStewardPatchesChange, onDetailChange, onReload }: {
  flowId: string
  detail: FlowLabDetail
  files: FlowFiles
  activeFile: string
  selectedNode: FlowNode | null
  validation: ValidationResponse | null
  inspectorTitle: string
  inspectorData: any
  stewardPatches: any[]
  onFilesChange: (value: any) => void
  onActiveFileChange: (key: string) => void
  onValidationChange: (value: ValidationResponse | null) => void
  onInspectorChange: (title: string, data: any) => void
  onStewardPatchesChange: (patches: any[]) => void
  onDetailChange: (value: any) => void
  onReload: () => Promise<void>
}) {
  return (
    <Grid gap={3} className="cf-advanced-grid">
      <VStack align="stretch" gap={3}>
        <FileEditor
          files={files}
          activeFile={activeFile}
          onActiveFileChange={onActiveFileChange}
          onFileChange={(key, content) => onFilesChange((prev: FlowFiles) => ({ ...prev, [key]: content }))}
          onSave={async (fileType, content) => {
            try {
              await saveLabFlowFile(flowId, fileType, content)
              showToast({ title: `${fileType} 已保存`, type: 'success' })
              await onReload()
            } catch (e: any) {
              showToast({ title: '保存失败', description: e.message, type: 'error' })
            }
          }}
          onValidate={async (currentFiles) => {
            try {
              const result = await validateLabFlow(flowId, currentFiles)
              onValidationChange(result)
              showToast({ title: result.valid ? '校验通过' : '校验失败', type: result.valid ? 'success' : 'error' })
            } catch (e: any) {
              showToast({ title: '校验失败', description: e.message, type: 'error' })
            }
          }}
          onPreviewGraph={async (currentFiles) => {
            try {
              const result = await previewLabFlowGraph(flowId, currentFiles)
              onDetailChange((prev: FlowLabDetail | null) => prev ? { ...prev, graph: result.graph } : prev)
              onInspectorChange('编辑预览', result.graph)
              showToast({ title: '链路图已预览', type: 'info' })
            } catch (e: any) {
              showToast({ title: '预览失败', description: e.message, type: 'error' })
            }
          }}
        />
        <ValidationCard validation={validation} />
      </VStack>
      <VStack align="stretch" gap={3}>
        <FlowSteward
          flowId={flowId}
          currentFiles={files}
          selectedNode={selectedNode}
          stewardMessage={detail.steward?.message || '描述你想调整的 Flow，生成可应用建议。'}
          contextKeys={detail.steward?.context_keys || []}
          patches={stewardPatches}
          onSuggestion={(data) => onStewardPatchesChange(data.patches || [])}
          onApply={(result) => {
            onFilesChange(result.files)
            onDetailChange((prev: FlowLabDetail | null) => prev ? { ...prev, graph: result.graph } : prev)
            onValidationChange(result.validation || { valid: true, errors: [], warnings: [], summary: '已应用' })
            onInspectorChange('应用结果', result)
            showToast({ title: result.summary || '已应用到编辑器', type: 'success' })
          }}
        />
        <Inspector title={inspectorTitle} data={inspectorData} />
      </VStack>
    </Grid>
  )
}

function FileEditor({ files, activeFile, onActiveFileChange, onFileChange, onSave, onValidate, onPreviewGraph }: {
  files: FlowFiles
  activeFile: string
  onActiveFileChange: (key: string) => void
  onFileChange: (key: string, content: string) => void
  onSave: (fileType: string, content: string) => void
  onValidate: (files: FlowFiles) => void
  onPreviewGraph: (files: FlowFiles) => void
}) {
  return (
    <Box p={4} className="cf-panel">
      <Text className="cf-kicker">Advanced</Text>
      <Heading size="sm" mb={3}>文件编辑器</Heading>
      <TabsRoot value={activeFile} onValueChange={(e) => onActiveFileChange(e.value)}>
        <TabsList>{FILE_TABS.map((tab) => <TabsTrigger key={tab.key} value={tab.key}>{tab.label}</TabsTrigger>)}</TabsList>
        {FILE_TABS.map((tab) => (
          <TabsContent key={tab.key} value={tab.key}>
            <VStack align="stretch" gap={3} mt={3}>
              <Textarea value={files[tab.key] || ''} onChange={(e) => onFileChange(tab.key, e.target.value)} rows={18} fontFamily="mono" fontSize="sm" />
              <HStack gap={2} flexWrap="wrap">
                <Button className="cf-accent-btn" onClick={() => onSave(tab.key, files[tab.key] || '')}>保存 {tab.label}</Button>
                <Button className="cf-outline-btn" onClick={() => onValidate(files)}>校验</Button>
                <Button className="cf-outline-btn" onClick={() => onPreviewGraph(files)}>预览链路图</Button>
              </HStack>
            </VStack>
          </TabsContent>
        ))}
      </TabsRoot>
    </Box>
  )
}

function FlowSteward({ flowId, currentFiles, selectedNode, stewardMessage, contextKeys, onSuggestion, onApply, patches }: {
  flowId: string
  currentFiles: FlowFiles
  selectedNode: FlowNode | null
  stewardMessage: string
  contextKeys: string[]
  onSuggestion: (data: StewardSuggestion) => void
  onApply: (result: any) => void
  patches: any[]
}) {
  const [intent, setIntent] = useState('')
  const [useLlm, setUseLlm] = useState(false)
  const [loading, setLoading] = useState(false)
  const [suggestion, setSuggestion] = useState<StewardSuggestion | null>(null)
  const [status, setStatus] = useState('')

  const suggest = async () => {
    setLoading(true)
    setStatus(useLlm ? '正在调用 LLM...' : '正在生成建议...')
    try {
      const data = await suggestFlowChanges(flowId, intent, currentFiles, selectedNode, useLlm)
      setSuggestion(data)
      onSuggestion(data)
      setStatus(data.summary || `建议已生成：${data.status}`)
    } catch (e: any) {
      setStatus(`生成失败：${e.message}`)
    } finally {
      setLoading(false)
    }
  }

  const apply = async () => {
    if (!patches.length) return
    setLoading(true)
    try {
      const result = await applyStewardPatches(flowId, currentFiles, patches, selectedNode)
      onApply(result)
      setStatus(result.summary || '已应用')
    } catch (e: any) {
      setStatus(`应用失败：${e.message}`)
      showToast({ title: '应用失败', description: e.message, type: 'error' })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Box p={4} className="cf-panel">
      <Text className="cf-kicker">Flow Steward</Text>
      <Heading size="sm" mb={2}>调整建议</Heading>
      <Text fontSize="sm" color="fg.muted" mb={3}>{stewardMessage}</Text>
      <HStack gap={1} flexWrap="wrap" mb={3}>{contextKeys.map((key) => <Badge key={key} className="cf-badge">{key}</Badge>)}</HStack>
      <VStack align="stretch" gap={3}>
        <Field.Root>
          <Field.Label>想怎么调整？</Field.Label>
          <Textarea value={intent} onChange={(e) => setIntent(e.target.value)} rows={3} placeholder="描述你想对 Flow 做的修改..." />
        </Field.Root>
        <label className="cf-checkbox">
          <input type="checkbox" checked={useLlm} onChange={(e) => setUseLlm(e.target.checked)} />
          <span>使用 LLM 生成建议</span>
        </label>
        <Button className="cf-accent-btn" onClick={suggest} loading={loading} loadingText="生成中...">生成建议</Button>
        {status && <Text fontSize="sm" color="fg.muted">{status}</Text>}
        {suggestion && (
          <Box p={3} className="cf-soft-panel">
            <Text fontWeight="semibold" mb={2}>{suggestion.summary || '建议计划'}</Text>
            <VStack align="stretch" gap={1}>{suggestion.steps.map((step, index) => <Text key={index} fontSize="sm">{index + 1}. {step}</Text>)}</VStack>
            {patches.length > 0 && <Button className="cf-outline-btn" mt={3} onClick={apply} loading={loading}>应用到编辑器</Button>}
          </Box>
        )}
      </VStack>
    </Box>
  )
}
