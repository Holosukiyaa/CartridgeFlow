import test from 'node:test'
import assert from 'node:assert/strict'
import { pathDiff, redact, semanticProjection } from '../src/model.ts'

test('redacts nested credential values while preserving reference metadata', () => {
  const output = redact({ provider: 'local', api_key: 'live-secret', nested: { token: 'abc', reference: 'env:MODEL_KEY' } }) as any
  assert.equal(output.api_key, '[redacted]'); assert.equal(output.nested.token, '[redacted]'); assert.equal(output.nested.reference, 'env:MODEL_KEY')
})
test('semantic projection retains topology and merges declared findings', () => {
  const projection = semanticProjection({ cartridge: { id: 'demo' }, graph: { nodes: [{ id: 'a' }], edges: [] }, compatibility: { findings: [{ code: 'a' }] } }, { findings: [{ code: 'b' }] }, { findings: [{ code: 'c' }] })
  assert.equal((projection.topology as any).node_count, 1); assert.equal((projection.diagnostics as any).findings.length, 3)
})
test('path diff reports exact leaf path', () => assert.deepEqual(pathDiff({ recipe: { temperature: 0.2 } }, { recipe: { temperature: 0.7 } }), [{ path: '$.recipe.temperature', before: 0.2, after: 0.7 }]))
