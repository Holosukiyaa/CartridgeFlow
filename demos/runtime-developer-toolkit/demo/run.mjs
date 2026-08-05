import { createHash, createPublicKey, verify } from 'node:crypto'
import { inflateRawSync } from 'node:zlib'
import { existsSync, mkdirSync, readFileSync, readdirSync, rmSync, statSync, writeFileSync } from 'node:fs'
import { basename, dirname, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

const CONTROL_FILES = new Set(['release.manifest.json', 'hashes.json'])
const SHA256 = /^sha256:[0-9a-f]{64}$/
const ID = /^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$/
const PRIVATE_HANDOFF_PATH = /(^|\/)(?:chat(?:[-_].*)?|conversations?|creator[-_]?sessions?|authoring[-_]?sessions?|authoring[-_]?repository|developer[-_]?repository|frontend[-_]?state|local[-_]?storage)(?:\/|\.|$)/i
const PRIVATE_HANDOFF_FIELD = /^(?:chat(?:[_-].*)?|conversations?(?:[_-].*)?|creator[_-]?sessions?(?:[_-].*)?|authoring[_-]?sessions?(?:[_-].*)?|authoring[_-]?repositories?|developer[_-]?repositories?|frontend[_-]?states?|local[_-]?storage)$/i

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

function assertPublicRuntimeHandoff(files) {
  for (const [name, bytes] of files.entries()) {
    if (PRIVATE_HANDOFF_PATH.test(name)) fail(`archive contains private authoring state: ${name}`)
    if (!name.endsWith('.json')) continue
    let value
    try { value = JSON.parse(bytes.toString('utf8')) } catch { continue }
    const inspect = (item, path) => {
      if (Array.isArray(item)) return item.forEach((entry, index) => inspect(entry, `${path}[${index}]`))
      if (!item || typeof item !== 'object') return
      for (const [key, child] of Object.entries(item)) {
        const childPath = `${path}.${key}`
        if (PRIVATE_HANDOFF_FIELD.test(key)) fail(`archive contains private authoring state: ${name}:${childPath}`)
        inspect(child, childPath)
      }
    }
    inspect(value, '$')
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
    const value = compression === 0 ? compressed : compression === 8 ? inflateRawSync(compressed, { maxOutputLength: 64 * 1024 * 1024 }) : fail(`unsupported ZIP compression for ${name}`)
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
  assertPublicRuntimeHandoff(files)
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
  const payloadEntries = hashes.files.filter((entry) => entry.path.startsWith('payload/')).sort((left, right) => (left.path < right.path ? -1 : left.path > right.path ? 1 : 0))
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
  const supportedFlowVersions = new Set(['1.0', '1.1', '1.6', '1.7'])
  const flowVersion = flow.protocol?.version
  if (release.runtime?.flow_contract?.id !== 'CF-FARP' || !supportedFlowVersions.has(release.runtime?.flow_contract?.version) || flow.protocol?.id !== 'CF-FARP' || !supportedFlowVersions.has(flowVersion) || release.runtime.flow_contract.version !== flowVersion) fail('payload does not declare one supported, matching CF-FARP runtime contract')
  if (flow.execution_plan?.schema !== 'cartridgeflow.execution_plan.v1' || !flow.states || !Array.isArray(flow.execution_plan.edges)) fail(`payload has no executable FARP@${flowVersion} execution plan`)
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

async function executeNode(state, nodeId, store, mock, runDirectory, tools) {
  // Decision (LLM) node
  if (state.type === 'process' && state.kind === 'decision' && state.executor === 'llm') {
    const output = state.output || state.params?.output || 'decision'
    // Platform semantics: the node's declared outputs.<name>.target.key is the
    // store key consumers bind to; state.output is only the raw envelope key.
    const targets = Object.values(state.outputs || {})
    const storeTarget = targets.map((target) => target?.target).find((target) => target?.type === 'store')
    const storeKey = storeTarget?.key || output
    // decision_contract.consume unwraps the envelope payload (payload_path).
    const contract = state.decision_contract || {}
    const consume = contract.consume || {}
    const unwrap = (envelope) => {
      if (consume.mode !== 'payload_path' || !consume.path || !envelope || typeof envelope !== 'object') return envelope
      let value = envelope
      for (const part of consume.path.split('.')) {
        if (value == null || typeof value !== 'object') return envelope
        value = value[part]
      }
      return value === undefined ? envelope : value
    }
    if (mock) {
      const offline = contract.offline_decision || {}
      store[storeKey] = unwrap(offline) ?? offline
      return
    }
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
    const content = body.choices?.[0]?.message?.content
    let envelope = body
    if (typeof content === 'string' && content.trim()) {
      try { envelope = JSON.parse(content) } catch { envelope = body }
    }
    store[storeKey] = unwrap(envelope)
    return
  }
  // MCP write node
  if (state.type === 'process' && state.kind === 'mcp_execute' && state.executor === 'mcp') {
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
    return
  }
  // Human review gate
  if (state.type === 'process' && (state.kind === 'human_gate' || state.action === 'confirm_checkpoint')) {
    const interaction = state.params?.interaction || {}
    const key = interaction.store_key || state.params?.output || 'approval'
    if (mock) {
      const answer = interaction.offline_answer || { approval: 'approved', feedback: '' }
      store[key] = answer
      for (const output of Object.values(state.outputs || {})) {
        if (output?.target?.type === 'store' && output.target.key) store[output.target.key] = answer
      }
      console.log(`[review] ${state.title || nodeId}: auto-approved (mock)`)
    } else {
      fail(`review node ${state.title || nodeId} requires interactive approval, which the minimal demo does not implement; run with --mock to auto-approve`)
    }
    return
  }
  // Template assembly: read template asset, substitute {{placeholder}} from store
  if (state.type === 'process' && state.action === 'render_template') {
    const params = state.params || {}
    let template = typeof params.template === 'string' ? params.template : ''
    const templateFile = params.template_file
    if (templateFile) {
      const packageRoot = resolve(runDirectory, 'package')
      const templatePath = resolve(packageRoot, String(templateFile).replace(/\\/g, '/'))
      if (templatePath !== packageRoot && !templatePath.startsWith(`${packageRoot}${sep}`)) {
        fail(`render_template template escapes package dir: ${templateFile}`)
      }
      if (!existsSync(templatePath)) fail(`render_template template file not found: ${templateFile}`)
      template = readFileSync(templatePath, 'utf8')
    }
    const variables = params.variables && typeof params.variables === 'object' ? params.variables : {}
    for (const [placeholder, storeKey] of Object.entries(variables)) {
      const value = store[storeKey]
      if (value === undefined || value === null) fail(`render_template missing store value: ${placeholder}(${storeKey})`)
      const text = typeof value === 'string' ? value : JSON.stringify(value, null, 2)
      template = template.split(`{{${placeholder}}}`).join(text)
    }
    store[params.output || 'rendered_template'] = template
    return
  }
  // Deterministic pass_result with artifact target
  if (state.type === 'process' && state.action === 'pass_result') {
    const preset = state.params?.preset_config || {}
    const inputBindings = Object.values(state.inputs || {})
      .map((input) => input?.binding?.key)
      .filter((key) => typeof key === 'string')
    const fromKey = state.params?.input || state.params?.from || preset.from || preset.source || preset.items
      || (inputBindings.length === 1 ? inputBindings[0] : undefined)
    const targets = Object.values(state.outputs || {})
    const storeTargets = targets.map((target) => target?.target).filter((target) => target?.type === 'store' && target.key)
    const artifactTarget = targets.map((target) => target?.target).find((target) => target?.type === 'artifact')
    if (!fromKey && storeTargets.length === 0 && !artifactTarget) {
      return
    }
    if (!fromKey) fail(`pass_result has no resolvable input source (params.input/preset/items or single inputs binding)`)
    const sourceKeys = typeof fromKey === 'string'
      ? fromKey.split(',').map((key) => key.trim()).filter(Boolean)
      : []
    const missingKeys = sourceKeys.filter((key) => store[key] === undefined)
    if ((storeTargets.length > 0 || artifactTarget) && missingKeys.length > 0) {
      fail(`pass_result is missing required store value: ${missingKeys.join(', ')}`)
    }
    const value = sourceKeys.length > 1
      ? Object.fromEntries(sourceKeys.map((key) => [key, store[key]]))
      : store[fromKey]
    if (value === undefined && (storeTargets.length > 0 || artifactTarget)) fail(`pass_result is missing required store value: ${fromKey}`)
    if (artifactTarget) {
      const fileName = String(artifactTarget.name || 'result.txt').replace(/\\/g, '/')
      if (!safePath(fileName)) fail(`artifact output path is unsafe: ${fileName}`)
      const output = resolve(runDirectory, 'artifacts', fileName)
      const artifactRoot = resolve(runDirectory, 'artifacts')
      if (!output.startsWith(`${artifactRoot}${sep}`)) fail('artifact output escapes the artifact directory')
      mkdirSync(dirname(output), { recursive: true })
      const content = typeof value === 'string' ? value : JSON.stringify(value ?? {}, null, 2)
      writeFileSync(output, content, 'utf8')
      store[artifactTarget.artifact_id || state.output || 'artifact'] = { path: `artifacts/${fileName}`, bytes: Buffer.byteLength(content) }
    }
    for (const target of storeTargets) store[target.key] = value
    return
  }
}

function evaluateLoopCondition(expression, store) {
  // Supports "$storeKey" and "$storeKey.field" (and nested dotted paths).
  if (typeof expression !== 'string' || !expression.startsWith('$')) return Boolean(expression)
  const path = expression.slice(1).split('.')
  let value = store
  for (const part of path) {
    if (value == null || typeof value !== 'object') return false
    value = value[part]
  }
  return Boolean(value)
}

async function executeFlow(manifest, flow, runDirectory, mock) {
  const states = flow.states
  const edges = new Map()
  const loopEdges = new Map()
  const forkEdges = new Map()
  const joinEdges = new Map()
  const joinEdgesByFrom = new Map()
  const failureEdges = new Map()
  const failureTargets = new Set()
  const executedBranches = new Map()
  for (const edge of flow.execution_plan.edges) {
    if (edge?.kind === 'sequence') {
      if (!edge.from || !edge.to || edges.has(edge.from)) fail('minimal runtime only accepts one sequence successor per state')
      edges.set(edge.from, edge.to)
    } else if (edge?.kind === 'loop') {
      if (!edge.from || !edge.to) fail('loop edge is missing from/to')
      loopEdges.set(edge.from, edge)
    } else if (edge?.kind === 'fork') {
      if (!edge.from || !edge.to) fail('fork edge is missing from/to')
      const list = forkEdges.get(edge.from) || []
      list.push(edge)
      forkEdges.set(edge.from, list)
    } else if (edge?.kind === 'join') {
      if (!edge.from || !edge.to) fail('join edge is missing from/to')
      const list = joinEdges.get(edge.to) || []
      list.push(edge)
      joinEdges.set(edge.to, list)
      const byFrom = joinEdgesByFrom.get(edge.from) || []
      byFrom.push(edge)
      joinEdgesByFrom.set(edge.from, byFrom)
    } else if (edge?.kind === 'failure') {
      if (!edge.from || !edge.to || failureEdges.has(edge.from)) fail('failure edge is missing from/to or is ambiguous')
      failureEdges.set(edge.from, edge)
      failureTargets.add(edge.to)
    }
  }
  const tools = new Map((manifest.mcp_tools || []).filter((tool) => tool?.id).map((tool) => [tool.id, tool]))
  const store = Object.create(null)
  const nodeLogs = []
  let current = flow.execution_plan.entry
  let routedFailure = ''
  const trace = []
  const recordLog = (entry) => {
    nodeLogs.push({ ts: new Date().toISOString(), ...entry })
  }
  recordLog({ event: 'run_started', node: current, action: 'entry', status: 'running' })
  for (let steps = 0; steps < Object.keys(states).length + 5; steps += 1) {
    const state = states[current]
    if (!state) fail(`execution plan references unknown state: ${current}`)
    trace.push(current)
    if (state.type === 'terminal') {
      const failed = failureTargets.has(current)
      recordLog({ event: 'node_started', node: current, action: 'terminal', status: 'running' })
      recordLog({ event: 'node_completed', node: current, action: 'terminal', status: failed ? 'failed' : 'completed' })
      recordLog({ event: failed ? 'run_failed' : 'run_completed', status: failed ? 'failed' : 'completed', ...(routedFailure ? { reason: routedFailure } : {}) })
      return { status: failed ? 'failed' : 'completed', trace, store, nodeLogs, ...(routedFailure ? { error: routedFailure } : {}) }
    }
    recordLog({ event: 'node_started', node: current, action: state.action || state.kind || state.type, status: 'running' })
    try {
      await executeNode(state, current, store, mock, runDirectory, tools)
    } catch (error) {
      const failure = failureEdges.get(current)
      recordLog({ event: 'node_failed', node: current, action: state.action || state.kind || state.type, status: 'failed', reason: error.message })
      if (!failure) {
        recordLog({ event: 'run_failed', status: 'failed', reason: error.message })
        throw error
      }
      routedFailure = error.message
      current = failure.to
      continue
    }
    recordLog({ event: 'node_completed', node: current, action: state.action || state.kind || state.type, status: 'completed', output: state.output || state.params?.output || '' })
    if (state.type !== 'system' && state.type !== 'control' && state.type !== 'process') {
      fail(`minimal runtime does not support node type ${state.type}`)
    }
    const forks = forkEdges.get(current)
    if (forks && forks.length > 1) {
      // Sequential simulation of the parallel branches: run each branch from
      // its first node until it reaches the shared join target, then continue.
      const forkId = forks[0].fork?.id
      let joinTarget = null
      for (const forkEdge of forks) {
        let branchNode = forkEdge.to
        let branchJoin = null
        let guard = 0
        const branchTrace = []
        while (branchNode && !branchJoin && guard < 100) {
          guard += 1
          branchTrace.push(branchNode)
          const branchState = states[branchNode]
          if (!branchState) fail(`branch references unknown state: ${branchNode}`)
          if (branchState.type === 'terminal') {
            recordLog({ event: 'run_completed', status: 'completed' })
            return { status: 'completed', trace: [...trace, ...branchTrace], store, nodeLogs }
          }
          recordLog({ event: 'branch_node_started', node: branchNode, branch: forkEdge.fork?.branch || '', action: branchState.action || branchState.kind || branchState.type, status: 'running' })
          await executeNode(branchState, branchNode, store, mock, runDirectory, tools)
          recordLog({ event: 'branch_node_completed', node: branchNode, branch: forkEdge.fork?.branch || '', action: branchState.action || branchState.kind || branchState.type, status: 'completed', output: branchState.output || branchState.params?.output || '' })
          const branchJoinEdges = joinEdgesByFrom.get(branchNode)
          if (branchJoinEdges && branchJoinEdges.length > 0) {
            branchJoin = branchJoinEdges[0]
            break
          }
          const branchForks = forkEdges.get(branchNode)
          if (branchForks && branchForks.length > 1) fail('nested forks are not supported by the minimal runtime')
          const branchLoop = loopEdges.get(branchNode)
          if (branchLoop) {
            const loop = branchLoop.loop || {}
            branchNode = evaluateLoopCondition(loop.continue_when, store) ? branchLoop.to : loop.exit_to
            continue
          }
          branchNode = edges.get(branchNode)
        }
        if (!branchJoin) fail(`branch ${forkEdge.fork?.branch || forkEdge.id} did not reach its join edge`)
        if (joinTarget === null) {
          joinTarget = branchJoin.to
        } else if (joinTarget !== branchJoin.to) {
          fail(`branches of fork ${forkId || forks[0].id} disagree on the join target`)
        }
        executedBranches.set(forkId || joinTarget, (executedBranches.get(forkId || joinTarget) || 0) + 1)
      }
      const totalBranches = (joinEdges.get(joinTarget) || []).length
      if (totalBranches > 1 && (executedBranches.get(forkId || joinTarget) || 0) < totalBranches) {
        fail(`join ${forkId || joinTarget} did not receive every branch`)
      }
      trace.push(joinTarget)
      current = joinTarget
    } else {
      current = edges.get(current)
      if (!current) {
        const loopEdge = loopEdges.get(current === undefined ? trace.at(-1) : current)
        if (loopEdge) {
          const loop = loopEdge.loop || {}
          const continueLoop = evaluateLoopCondition(loop.continue_when, store)
          current = continueLoop ? loopEdge.to : loop.exit_to
        }
      }
    }
    if (!current) fail(`state ${trace.at(-1)} has no sequence successor`)
  }
  recordLog({ event: 'run_failed', status: 'failed', reason: 'execution plan exceeded its bounded step count' })
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
  const artifacts = []
  const artifactRoot = join(runRoot, 'artifacts')
  if (existsSync(artifactRoot)) {
    for (const name of readdirSync(artifactRoot)) {
      const full = join(artifactRoot, name)
      if (statSync(full).isFile()) artifacts.push({ name, bytes: statSync(full).size, path: `artifacts/${name}` })
    }
  }
  const runLog = {
    release_id: result.release.release_id,
    signer: result.signer,
    cartridge: `${result.manifest.id}@${result.manifest.version}`,
    mode: mock ? 'mock' : 'http',
    started_at: execution.nodeLogs?.[0]?.ts || new Date().toISOString(),
    artifacts,
    logs: execution.nodeLogs || [],
  }
  writeFileSync(join(runRoot, 'run-log.jsonl'), `${execution.nodeLogs.map((entry) => JSON.stringify(entry)).join('\n')}\n`, 'utf8')
  writeFileSync(join(runRoot, 'run-result.json'), `${JSON.stringify({ release_id: result.release.release_id, installed: basename(installed), status: execution.status, trace: execution.trace, store: execution.store, artifacts, ...(execution.error ? { error: execution.error } : {}) }, null, 2)}\n`, 'utf8')
  // cmd-list style runtime panel output
  console.log('=== CartridgeFlow Runtime (demo) ===')
  console.log(`release : ${runLog.release_id}`)
  console.log(`signer  : ${runLog.signer}`)
  console.log(`cartridge: ${runLog.cartridge}`)
  console.log(`mode    : ${runLog.mode}`)
  console.log(`status  : ${execution.status}`)
  console.log('--- node execution list ---')
  let index = 0
  const logs = execution.nodeLogs || []
  for (const entry of logs) {
    if (!entry.event.startsWith('node_') && !entry.event.startsWith('branch_node_')) continue
    if (!entry.event.endsWith('_started')) continue
    index += 1
    const action = entry.action || ''
    const completed = logs.find((item) => item.node === entry.node && item.event === entry.event.replace('_started', '_completed'))
    const output = completed?.output ? ` -> ${completed.output}` : ''
    console.log(`[${String(index).padStart(2, ' ')}] ${entry.node} (${action})${output}`)
  }
  console.log('--- artifacts ---')
  if (artifacts.length === 0) console.log('  (none)')
  for (const artifact of artifacts) console.log(`  ${artifact.name} (${artifact.bytes} bytes)`)
  console.log(`log     : run-log.jsonl (${execution.nodeLogs.length} entries)`)
  if (execution.status !== 'completed') process.exitCode = 1
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main(process.argv.slice(2)).catch((error) => {
    try {
      const positional = process.argv.slice(2).filter((value) => !value.startsWith('--'))
      if (positional[0] === 'run' && positional[2]) {
        const runRoot = resolve(positional[2])
        mkdirSync(runRoot, { recursive: true })
        writeFileSync(join(runRoot, 'run-log.jsonl'), `${JSON.stringify({ ts: new Date().toISOString(), event: 'run_failed', status: 'failed', reason: error.message })}\n`, 'utf8')
      }
    } catch { /* log write is best-effort */ }
    console.error(JSON.stringify({ ok: false, error: error.message }, null, 2))
    process.exitCode = 1
  })
}

export { assertPublicRuntimeHandoff, executeFlow, verifyArchive }
