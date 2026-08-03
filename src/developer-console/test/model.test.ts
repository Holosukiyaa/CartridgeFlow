import test from 'node:test'
import assert from 'node:assert/strict'
import { pathDiff, redact, semanticProjection } from '../src/model.ts'

test('redacts nested credential values while preserving reference metadata', () => {
  const output = redact({ provider: 'local', api_key: 'live-secret', nested: { token: 'abc', reference: 'env:MODEL_KEY' } }) as any
  assert.equal(output.api_key, '[redacted]'); assert.equal(output.nested.token, '[redacted]'); assert.equal(output.nested.reference, 'env:MODEL_KEY')
})
test('redacts sensitive URL query values without changing non-sensitive query values', () => {
  const output = redact('https://api.example.test/v1?token=plain-text-secret&region=cn')
  assert.equal(output, 'https://api.example.test/v1?token=[redacted]&region=cn')
})
test('redacts URL user-info passwords', () => {
  assert.equal(redact('https://user:plain-text-secret@example.test/v1'), 'https://user:[redacted]@example.test/v1')
})
test('redacts bearer tokens', () => {
  assert.equal(redact('Bearer plain-text-secret'), 'Bearer [redacted]')
})
test('keeps non-sensitive URLs unchanged', () => {
  assert.equal(redact('https://assets.example.test/images/report.png?version=2'), 'https://assets.example.test/images/report.png?version=2')
})
test('semantic projection retains topology and merges declared findings', () => {
  const projection = semanticProjection({ cartridge: { id: 'demo' }, graph: { nodes: [{ id: 'a' }], edges: [] }, compatibility: { findings: [{ code: 'a' }] } }, { findings: [{ code: 'b' }] }, { findings: [{ code: 'c' }] })
  assert.equal((projection.topology as any).node_count, 1); assert.equal((projection.diagnostics as any).findings.length, 3)
})
test('path diff reports exact leaf path', () => assert.deepEqual(pathDiff({ recipe: { temperature: 0.2 } }, { recipe: { temperature: 0.7 } }), [{ path: '$.recipe.temperature', before: 0.2, after: 0.7 }]))
