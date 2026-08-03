import assert from 'node:assert/strict'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import { assertPublicRuntimeHandoff, verifyArchive } from '../run.mjs'

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
