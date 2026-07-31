import { createHash, createPublicKey, verify } from 'node:crypto'
import { inflateRawSync } from 'node:zlib'
import { existsSync, mkdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve, sep } from 'node:path'

const CONTROL_FILES = new Set(['release.manifest.json', 'hashes.json'])
const SHA256 = /^sha256:[0-9a-f]{64}$/
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/

function fail(message) {
  throw new Error(message)
}

function safePath(value) {
  return Boolean(value) && !value.includes('\\') && !value.startsWith('/') && !value.split('/').some((part) => !part || part === '.' || part === '..')
}

function sha256(value) {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`
}

function parseJson(bytes, label) {
  try {
    const value = JSON.parse(bytes.toString('utf8'))
    if (!value || typeof value !== 'object' || Array.isArray(value)) fail(`${label} must be a JSON object`)
    return value
  } catch (error) {
    fail(`${label} is not valid UTF-8 JSON: ${error.message}`)
  }
}

function readZip(archivePath) {
  const bytes = readFileSync(archivePath)
  let eocd = -1
  for (let index = bytes.length - 22; index >= Math.max(0, bytes.length - 65557); index -= 1) {
    if (bytes.readUInt32LE(index) === 0x06054b50) { eocd = index; break }
  }
  if (eocd < 0) fail('archive has no ZIP end-of-central-directory record')
  const count = bytes.readUInt16LE(eocd + 10)
  const centralOffset = bytes.readUInt32LE(eocd + 16)
  const files = new Map()
  let cursor = centralOffset
  for (let entry = 0; entry < count; entry += 1) {
    if (bytes.readUInt32LE(cursor) !== 0x02014b50) fail('archive central directory is invalid')
    const compression = bytes.readUInt16LE(cursor + 10)
    const compressedSize = bytes.readUInt32LE(cursor + 20)
    const uncompressedSize = bytes.readUInt32LE(cursor + 24)
    const nameLength = bytes.readUInt16LE(cursor + 28)
    const extraLength = bytes.readUInt16LE(cursor + 30)
    const commentLength = bytes.readUInt16LE(cursor + 32)
    const localOffset = bytes.readUInt32LE(cursor + 42)
    const name = bytes.subarray(cursor + 46, cursor + 46 + nameLength).toString('utf8')
    cursor += 46 + nameLength + extraLength + commentLength
    if (name.endsWith('/')) continue
    if (!safePath(name) || files.has(name)) fail(`archive contains an unsafe or duplicate path: ${name}`)
    if (bytes.readUInt32LE(localOffset) !== 0x04034b50) fail(`archive local entry is invalid: ${name}`)
    const localNameLength = bytes.readUInt16LE(localOffset + 26)
    const localExtraLength = bytes.readUInt16LE(localOffset + 28)
    const start = localOffset + 30 + localNameLength + localExtraLength
    const compressed = bytes.subarray(start, start + compressedSize)
    const value = compression === 0 ? compressed : compression === 8 ? inflateRawSync(compressed) : fail(`unsupported ZIP compression for ${name}`)
    if (value.length !== uncompressedSize) fail(`ZIP size mismatch for ${name}`)
    files.set(name, value)
  }
  return files
}

function canonicalPayloadEntries(entries) {
  return JSON.stringify(entries.map(({ path, sha256: digest, size }) => ({ path, sha256: digest, size })))
}

function trustedKeys(trustPath) {
  if (!trustPath) return new Map()
  const value = parseJson(readFileSync(trustPath), 'trust store')
  if (value.schema !== 'cartridgeflow.release_trust_store.v1' || !Array.isArray(value.keys)) fail('trust store schema is invalid')
  return new Map(value.keys.filter((item) => item && ID.test(item.key_id || '') && typeof item.public_key === 'string').map((item) => [item.key_id, item.public_key]))
}

function verifyArchive(archivePath, trustPath) {
  const files = readZip(archivePath)
  for (const required of ['release.manifest.json', 'hashes.json', 'public/experience.json', 'public/delivery.contract.json', 'payload/manifest.json', 'payload/root.flow.json']) {
    if (!files.has(required)) fail(`archive is missing ${required}`)
  }
  const releaseBytes = files.get('release.manifest.json')
  const hashesBytes = files.get('hashes.json')
  const release = parseJson(releaseBytes, 'release.manifest.json')
  const hashes = parseJson(hashesBytes, 'hashes.json')
  if (release.schema !== 'cartridgeflow.release_envelope.v1' || hashes.schema !== 'cartridgeflow.release_hashes.v1' || !Array.isArray(hashes.files)) fail('archive has an unsupported CF-CRE contract')
  if (sha256(hashesBytes) !== release.integrity?.content_digest) fail('hashes.json does not match release content_digest')
  const listed = new Set()
  for (const entry of hashes.files) {
    if (!entry || !safePath(entry.path) || !SHA256.test(entry.sha256 || '') || !Number.isInteger(entry.size) || entry.size < 0) fail('hashes.json contains an invalid file entry')
    if (CONTROL_FILES.has(entry.path) || entry.path.startsWith('signatures/') || listed.has(entry.path)) fail(`hashes.json contains an invalid path: ${entry.path}`)
    const content = files.get(entry.path)
    if (!content || content.length !== entry.size || sha256(content) !== entry.sha256) fail(`archive digest mismatch: ${entry.path}`)
    listed.add(entry.path)
  }
  for (const name of files.keys()) {
    if (!CONTROL_FILES.has(name) && !name.startsWith('signatures/') && !listed.has(name)) fail(`archive file is not listed in hashes.json: ${name}`)
  }
  const payloadEntries = hashes.files.filter((entry) => entry.path.startsWith('payload/')).sort((left, right) => left.path.localeCompare(right.path))
  if (sha256(Buffer.from(canonicalPayloadEntries(payloadEntries), 'utf8')) !== release.payload?.digest) fail('payload digest does not match hashes.json')
  const descriptor = (release.signatures || []).find((item) => item?.role === 'publisher')
  if (!descriptor || descriptor.algorithm !== 'ed25519' || !ID.test(descriptor.key_id || '') || !files.has(descriptor.path)) fail('archive has no valid publisher signature descriptor')
  const signature = parseJson(files.get(descriptor.path), 'publisher signature')
  if (signature.schema !== 'cartridgeflow.release_signature.v1' || signature.key_id !== descriptor.key_id || signature.algorithm !== 'ed25519') fail('publisher signature metadata does not match the release')
  const publicKey = Buffer.from(signature.public_key || '', 'base64')
  const signatureBytes = Buffer.from(signature.signature || '', 'base64')
  if (publicKey.length !== 32 || signatureBytes.length !== 64 || JSON.stringify(signature.signed_files) !== JSON.stringify(['release.manifest.json', 'hashes.json'])) fail('publisher signature encoding is invalid')
  const spki = Buffer.concat([Buffer.from('302a300506032b6570032100', 'hex'), publicKey])
  if (!verify(null, Buffer.concat([releaseBytes, Buffer.from('\n'), hashesBytes]), createPublicKey({ key: spki, format: 'der', type: 'spki' }), signatureBytes)) fail('publisher Ed25519 signature verification failed')
  const trusted = trustedKeys(trustPath).get(descriptor.key_id)
  if (!trusted || !Buffer.from(trusted, 'base64').equals(publicKey)) fail(`publisher key is not trusted: ${descriptor.key_id}`)
  const manifest = parseJson(files.get('payload/manifest.json'), 'payload/manifest.json')
  const flow = parseJson(files.get('payload/root.flow.json'), 'payload/root.flow.json')
  if (release.runtime?.flow_contract?.id !== 'CF-FARP' || release.runtime?.flow_contract?.version !== '1.0' || flow.protocol?.id !== 'CF-FARP' || flow.protocol?.version !== '1.0') fail('payload does not declare the CF-FARP@1.0 runtime contract')
  if (flow.execution_plan?.schema !== 'cartridgeflow.execution_plan.v1' || !flow.states || !Array.isArray(flow.execution_plan.edges)) fail('payload has no executable FARP@1.0 execution plan')
  return { files, release, manifest, flow, signer: descriptor.key_id }
}

function writePayload(files, destination) {
  const target = resolve(destination)
  if (existsSync(target)) rmSync(target, { recursive: true, force: true })
  mkdirSync(target, { recursive: true })
  for (const [name, value] of files.entries()) {
    if (!name.startsWith('payload/')) continue
    const relative = name.slice('payload/'.length)
    if (!safePath(relative)) fail(`unsafe payload path: ${relative}`)
    const output = resolve(target, relative)
    if (output !== target && !output.startsWith(`${target}${sep}`)) fail(`payload escapes destination: ${relative}`)
    mkdirSync(dirname(output), { recursive: true })
    writeFileSync(output, value)
  }
  return target
}

function valueFromStore(value, store) {
  return typeof value === 'string' && value.startsWith('store:') ? store[value.slice('store:'.length)] ?? '' : value
}

async function executeFlow(manifest, flow, runDirectory, mock) {
  const states = flow.states
  const edges = new Map()
  for (const edge of flow.execution_plan.edges) {
    if (edge?.kind !== 'sequence') continue
    if (!edge.from || !edge.to || edges.has(edge.from)) fail('minimal runtime only accepts one sequence successor per state')
    edges.set(edge.from, edge.to)
  }
  const tools = new Map((manifest.mcp_tools || []).filter((tool) => tool?.id).map((tool) => [tool.id, tool]))
  const store = {}
  let current = flow.execution_plan.entry
  const trace = []
  for (let steps = 0; steps < Object.keys(states).length + 5; steps += 1) {
    const state = states[current]
    if (!state) fail(`execution plan references unknown state: ${current}`)
    trace.push(current)
    if (state.type === 'terminal') return { status: 'completed', trace, store }
    if (state.type === 'process' && state.kind === 'decision' && state.executor === 'llm') {
      const output = state.output || state.params?.output || 'decision'
      if (mock) {
        store[output] = state.mock_decision_envelope || state.params?.mock_decision_envelope || { status: 'resolved', value: 'mock model response' }
      } else {
        const baseUrl = process.env.CF_RUNTIME_MODEL_BASE_URL
        const apiKey = process.env.CF_RUNTIME_MODEL_API_KEY
        const model = process.env.CF_RUNTIME_MODEL
        if (!baseUrl || !apiKey || !model) fail('model API configuration is missing; use --mock or set CF_RUNTIME_MODEL_*')
        const response = await fetch(`${baseUrl.replace(/\/$/, '')}/chat/completions`, {
          method: 'POST',
          headers: { authorization: `Bearer ${apiKey}`, 'content-type': 'application/json' },
          body: JSON.stringify({ model, messages: [{ role: 'user', content: state.prompt || state.params?.prompt || 'Complete this cartridge task.' }] }),
        })
        if (!response.ok) fail(`model API returned HTTP ${response.status}`)
        const body = await response.json()
        store[output] = body.choices?.[0]?.message?.content ?? body
      }
    } else if (state.type === 'process' && state.kind === 'mcp_execute' && state.executor === 'mcp') {
      const toolId = (state.allowed_tools || state.params?.allowed_tools || [])[0]
      const tool = tools.get(toolId)
      if (!tool || tool.id !== 'filesystem_write') fail('minimal runtime only supports the portable filesystem_write MCP tool')
      const params = state.params || {}
      const config = params.preset_config || {}
      const path = String(config.path || tool.default_params?.path || 'result.txt').replace(/\\/g, '/')
      if (!safePath(path)) fail(`MCP output path is unsafe: ${path}`)
      const content = String(valueFromStore(config.content ?? tool.default_params?.content ?? '', store))
      const output = resolve(runDirectory, 'artifacts', path)
      const artifactRoot = resolve(runDirectory, 'artifacts')
      if (!output.startsWith(`${artifactRoot}${sep}`)) fail('MCP output escapes the artifact directory')
      mkdirSync(dirname(output), { recursive: true })
      writeFileSync(output, content, 'utf8')
      store[state.output || params.output || 'mcp_result'] = { path: `artifacts/${path}`, bytes: Buffer.byteLength(content) }
    } else if (state.type !== 'system' && state.type !== 'control' && state.type !== 'process') {
      fail(`minimal runtime does not support node type ${state.type}`)
    }
    current = edges.get(current)
    if (!current) fail(`state ${trace.at(-1)} has no sequence successor`)
  }
  fail('execution plan exceeded its bounded step count')
}

async function main(args) {
  const [command, archive, destination] = args.filter((value) => !value.startsWith('--'))
  const trustIndex = args.indexOf('--trust')
  const trustPath = trustIndex >= 0 ? args[trustIndex + 1] : ''
  const mock = args.includes('--mock')
  if (!['verify', 'install', 'run'].includes(command) || !archive || ((command === 'install' || command === 'run') && !destination) || (trustIndex >= 0 && !trustPath)) {
    fail('usage: verify <archive> --trust <trust.json> | install <archive> <destination> --trust <trust.json> | run <archive> <run-directory> --trust <trust.json> --mock')
  }
  const result = verifyArchive(archive, trustPath)
  if (command === 'verify') {
    console.log(JSON.stringify({ ok: true, protocol: 'CF-CRE@1', release_id: result.release.release_id, signer: result.signer }, null, 2))
    return
  }
  if (command === 'install') {
    const installed = writePayload(result.files, destination)
    console.log(JSON.stringify({ ok: true, installed, release_id: result.release.release_id }, null, 2))
    return
  }
  const runRoot = resolve(destination)
  mkdirSync(runRoot, { recursive: true })
  const installed = writePayload(result.files, join(runRoot, 'package'))
  const execution = await executeFlow(result.manifest, result.flow, runRoot, mock)
  writeFileSync(join(runRoot, 'run-result.json'), `${JSON.stringify({ release_id: result.release.release_id, installed: basename(installed), ...execution }, null, 2)}\n`, 'utf8')
  console.log(JSON.stringify({ ok: true, release_id: result.release.release_id, ...execution }, null, 2))
}

main(process.argv.slice(2)).catch((error) => {
  console.error(JSON.stringify({ ok: false, error: error.message }, null, 2))
  process.exitCode = 1
})
