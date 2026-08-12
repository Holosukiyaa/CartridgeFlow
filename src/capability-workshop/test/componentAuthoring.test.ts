import test from 'node:test'
import assert from 'node:assert/strict'
import { componentSlug, displaySources, generatedComponentDraft, mockDisplayValue, nextComponentId } from '../src/componentAuthoring.ts'

test('builds display sources from public inputs and typed node outputs', () => {
  const sources = displaySources({ nodes: [{ id: 'build', title: '生成结果', outputs: {
    summary: { schema: { title: '摘要' }, target: { type: 'store', key: 'summary' } },
    report: { schema: { title: '报告' }, target: { type: 'artifact', artifact_id: 'report.html' } },
  } }] }, [{ id: 'topic', label: '主题' }])
  assert.ok(sources.some((item) => item.value === 'store:topic' && item.label === '主题'))
  assert.ok(sources.some((item) => item.value === 'store:summary' && item.label === '生成结果 / 摘要'))
  assert.ok(!sources.some((item) => item.value.startsWith('artifact:')))
})

test('restores only generated component metadata into the editor', () => {
  assert.equal(generatedComponentDraft({ id: 'legacy' }), null)
  assert.deepEqual(generatedComponentDraft({ authoring: { kind: 'passive_display_v1', template_id: 'list', fields: [{ id: 'items', label: '条目', type: 'list', source: 'store:items' }] } }), {
    templateId: 'list', fields: [{ id: 'items', label: '条目', type: 'list', required: false, source: 'store:items' }],
  })
})

test('preview values cover normal, long and empty states', () => {
  const field = { id: 'items', label: '条目', type: 'list' as const, required: false, source: 'store:items' }
  assert.equal((mockDisplayValue(field, 'normal') as unknown[]).length, 3)
  assert.equal((mockDisplayValue(field, 'long') as unknown[]).length, 3)
  assert.deepEqual(mockDisplayValue(field, 'empty'), [])
  assert.equal(componentSlug('结果 面板'), '')
  assert.equal(componentSlug('Result Panel'), 'result.panel')
  assert.equal(nextComponentId(['result.panel', 'result.panel.2']), 'result.panel.3')
})
