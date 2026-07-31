import { createServer } from 'node:http'

const port = Number(process.env.CF_DEMO_MODEL_PORT || 11434)
const expectedKey = process.env.CF_DEMO_MODEL_API_KEY || 'cf-demo-key'

createServer((request, response) => {
  if (request.method !== 'POST' || request.url !== '/v1/chat/completions') {
    response.writeHead(404).end()
    return
  }
  if (request.headers.authorization !== `Bearer ${expectedKey}`) {
    response.writeHead(401, { 'content-type': 'application/json' }).end(JSON.stringify({ error: { message: 'invalid API key' } }))
    return
  }
  let body = ''
  request.setEncoding('utf8')
  request.on('data', (chunk) => { body += chunk })
  request.on('end', () => {
    try { JSON.parse(body) } catch { response.writeHead(400).end(); return }
    const content = JSON.stringify({
      schema: 'decision_envelope.v1',
      status: 'resolved',
      summary: 'Local acceptance model response',
      payload: { decision: 'The model API node completed through the OpenAI-compatible contract.' },
    })
    response.writeHead(200, { 'content-type': 'application/json' }).end(JSON.stringify({
      id: 'cf-demo-response',
      object: 'chat.completion',
      choices: [{ index: 0, message: { role: 'assistant', content }, finish_reason: 'stop' }],
    }))
  })
}).listen(port, '127.0.0.1', () => {
  console.log(`CF demo OpenAI-compatible model API listening on 127.0.0.1:${port}`)
})
