import test from 'node:test'
import assert from 'node:assert/strict'
import { buildNodePresentationFiles, nodeSettingDrafts } from '../src/settingsPresentation.ts'

const files = {
  settings_contract: JSON.stringify({
    schema: 'cartridgeflow.cartridge_settings.v1',
    storage_scope: 'cartridge',
    fields: [
      { id: 'other.enabled', label: '其他节点开关', type: 'boolean', default: true },
      { id: 'brief.length', label: '简报长度', description: '控制输出篇幅', type: 'enum', default: 'normal', options: [{ value: 'short', label: '精简' }, { value: 'normal', label: '标准' }] },
    ],
  }),
  settings_bindings: JSON.stringify({
    schema: 'cartridgeflow.cartridge_settings_bindings.v1',
    bindings: [
      { setting_id: 'other.enabled', target: { kind: 'process_param', node_id: 'other', param: 'enabled' } },
      { setting_id: 'brief.length', target: { kind: 'process_param', node_id: 'generate', param: 'length' } },
    ],
  }),
  ui_contract: JSON.stringify({ schema: 'cartridgeflow.cartridge_ui.v1', mode: 'none', host_capabilities: [] }),
}

test('projects only the selected node bindings into editable drafts', () => {
  const result = nodeSettingDrafts(files, 'generate', { length: 'normal', max_points: 5, include_actions: true })
  assert.deepEqual(result.errors, [])
  assert.equal(result.drafts.length, 3)
  assert.deepEqual(result.drafts.map((item) => [item.param, item.type, item.exposed]), [
    ['include_actions', 'boolean', false],
    ['length', 'enum', true],
    ['max_points', 'integer', false],
  ])
  assert.equal(result.drafts[1].optionsText, 'short | 精简\nnormal | 标准')
})

test('builds v1 public fields and private node bindings without changing other nodes', () => {
  const drafts = nodeSettingDrafts(files, 'generate', { length: 'normal', max_points: 5 }).drafts
  const maxPoints = drafts.find((item) => item.param === 'max_points')!
  maxPoints.exposed = true
  maxPoints.label = '要点上限'
  const output = buildNodePresentationFiles(files, 'generate', { length: 'normal', max_points: 5 }, drafts)
  const settings = JSON.parse(output.settings_contract)
  const bindings = JSON.parse(output.settings_bindings)

  assert.equal(settings.schema, 'cartridgeflow.cartridge_settings.v1')
  assert.deepEqual(settings.fields.map((item: any) => item.id), ['other.enabled', 'brief.length', 'generate.max_points'])
  assert.equal(settings.fields[2].default, 5)
  assert.equal(settings.fields[2].node_id, undefined)
  assert.deepEqual(bindings.bindings[0], { setting_id: 'other.enabled', target: { kind: 'process_param', node_id: 'other', param: 'enabled' } })
  assert.deepEqual(bindings.bindings[2], { setting_id: 'generate.max_points', target: { kind: 'process_param', node_id: 'generate', param: 'max_points' } })
})

test('rejects an unpublished settings generation', () => {
  const v2 = { ...files, settings_contract: JSON.stringify({ schema: 'cartridgeflow.cartridge_settings.v2', storage_scope: 'cartridge', fields: [] }) }
  assert.match(nodeSettingDrafts(v2, 'generate', {}).errors[0], /cartridge_settings\.v1/)
  assert.throws(() => buildNodePresentationFiles(v2, 'generate', {}, []), /cartridge_settings\.v1/)
})

test('rejects enum controls whose current parameter has no matching option', () => {
  const drafts = nodeSettingDrafts({}, 'generate', { style: 'formal' }).drafts
  drafts[0] = { ...drafts[0], exposed: true, type: 'enum', optionsText: 'brief | 简洁' }
  assert.throws(() => buildNodePresentationFiles({}, 'generate', { style: 'formal' }, drafts), /当前参数值必须出现在选项中/)
})
