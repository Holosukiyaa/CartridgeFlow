import assert from 'node:assert/strict'
import { mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { assertPublicRuntimeHandoff, executeFlow, verifyArchive } from '../run.mjs'

const toolkitDirectory = fileURLToPath(new URL('../..', import.meta.url))
const sample = `${toolkitDirectory}/samples/dev.cf-cre-farp-acceptance-1.0.0.cf-cre.zip`
const trust = `${toolkitDirectory}/samples/trusted_publishers.json`

test('runtime accepts a public signed cartridge handoff', () => {
  const result = verifyArchive(sample, trust)
  assert.equal(result.release.runtime.flow_contract.id, 'CF-FARP')
  assert.equal(result.signer, 'local.development')
})

test('runtime rejects creator and developer private state before verification', () => {
  for (const [name, payload] of [
    ['payload/creator-session.json', '{}'],
    ['payload/manifest.json', JSON.stringify({ authoring_session: { intent: 'private' } })],
    ['payload/manifest.json', JSON.stringify({ developer_repositories: [{ id: 'private' }] })],
    ['payload/manifest.json', JSON.stringify({ frontend_state: { selectedPanel: 'creator' } })],
  ]) {
    assert.throws(() => assertPublicRuntimeHandoff(new Map([[name, Buffer.from(payload, 'utf8')]])), /private authoring state/)
  }
})

test('runtime propagates a reviewed public result through pass_result', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cartridgeflow-demo-'))
  try {
    const flow = {
      states: {
        start: { type: 'control' },
        review: {
          type: 'process', kind: 'human_gate', action: 'confirm_checkpoint',
          params: { interaction: { store_key: 'review_response', offline_answer: { approval: 'approved', feedback: '' } } },
          outputs: { review_result: { target: { type: 'store', key: 'review_result' } } },
        },
        persist: {
          type: 'process', kind: 'transfer', action: 'pass_result', params: { input: 'review_result', output: 'result' },
          outputs: { result: { target: { type: 'store', key: 'result' } } },
        },
        complete: { type: 'terminal' },
      },
      execution_plan: {
        entry: 'start',
        edges: [
          { kind: 'sequence', from: 'start', to: 'review' },
          { kind: 'sequence', from: 'review', to: 'persist' },
          { kind: 'sequence', from: 'persist', to: 'complete' },
        ],
      },
    }
    const result = await executeFlow({}, flow, directory, true)
    assert.equal(result.status, 'completed')
    assert.deepEqual(result.store.result, { approval: 'approved', feedback: '' })
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})

test('runtime routes a missing pass_result input to the declared failure exit', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'cartridgeflow-demo-'))
  try {
    const flow = {
      states: {
        start: { type: 'control' },
        review: {
          type: 'process', kind: 'human_gate', action: 'confirm_checkpoint',
          params: { interaction: { store_key: 'present', offline_answer: 'available' } },
          outputs: { present: { target: { type: 'store', key: 'present' } } },
        },
        persist: {
          type: 'process', kind: 'transfer', action: 'pass_result', params: { input: 'present, missing', output: 'result' },
          outputs: { result: { target: { type: 'store', key: 'result' } } },
        },
        complete: { type: 'terminal' },
        failed: { type: 'terminal' },
      },
      execution_plan: {
        entry: 'start',
        edges: [
          { kind: 'sequence', from: 'start', to: 'review' },
          { kind: 'sequence', from: 'review', to: 'persist' },
          { kind: 'sequence', from: 'persist', to: 'complete' },
          { kind: 'failure', from: 'persist', to: 'failed' },
        ],
      },
    }
    const result = await executeFlow({}, flow, directory, true)
    assert.equal(result.status, 'failed')
    assert.match(result.error, /missing required store value/)
    assert.deepEqual(result.trace, ['start', 'review', 'persist', 'failed'])
    assert.equal(result.store.result, undefined)
  } finally {
    rmSync(directory, { recursive: true, force: true })
  }
})
