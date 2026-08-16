import test from 'node:test'
import assert from 'node:assert/strict'
import { buildTextVerificationPatch, buildVerificationCases, isCurrentVerification, runDiagnosis, updateVerificationInput } from '../src/verificationExperience'

test('wires the guided text input through a typed result output', () => {
  const patch = buildTextVerificationPatch({ params: { node_category: 'transfer' }, outputs: {} }, [{ id: 'content' }])
  assert.equal(patch.manifestInputs[1]?.id, 'content_2')
  assert.equal(patch.manifestInputs[1]?.required, true)
  assert.deepEqual(patch.params, { node_category: 'transfer', input: 'content_2', output: 'result' })
  assert.deepEqual(patch.inputs.content, { required: true, schema: { type: 'string' }, binding: { source: 'run_input', key: 'content_2' } })
  assert.deepEqual(patch.outputs.result, { schema: { type: 'string' }, target: { type: 'store', key: 'result' } })
})

test('builds typed success data and a safe missing-required failure', () => {
  const cases = buildVerificationCases([
    { id: 'topic', type: 'text', required: true },
    { id: 'count', type: 'number', default: 3 },
    { id: 'enabled', type: 'boolean' },
  ])
  assert.deepEqual(cases.success, { topic: '验收输入', count: 3, enabled: true })
  assert.deepEqual(cases.failure, { topic: null, count: 3, enabled: true })
  assert.equal(cases.failureField?.id, 'topic')
})

test('keeps edited verification inputs typed', () => {
  assert.deepEqual(updateVerificationInput({}, { id: 'count', type: 'number' }, '12'), { count: 12 })
  assert.deepEqual(updateVerificationInput({}, { id: 'tags', type: 'string_list' }, 'a\nb'), { tags: ['a', 'b'] })
  assert.deepEqual(updateVerificationInput({}, { id: 'enabled', type: 'boolean' }, false), { enabled: false })
})

test('projects runtime errors to a stable owner-first diagnosis', () => {
  const result = runDiagnosis({ status: 'failed', run_id: 'run_1', error: { code: 'INPUT_REQUIRED', node_id: 'collect', message: 'topic is required' } })
  assert.equal(result.title, 'INPUT_REQUIRED · collect')
  assert.equal(result.detail, 'topic is required')
  assert.equal(result.tone, 'failure')
})

test('only current evidence unlocks release', () => {
  assert.equal(isCurrentVerification({ status: 'current', verification: { token: 'verify_123' } }), true)
  assert.equal(isCurrentVerification({ status: 'stale', verification: { token: 'verify_123' } }), false)
})
