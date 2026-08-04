import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

const creator = (overrides = {}) => ({
  session_id: 's1', revision: 1, intent: 'Create a clear story',
  semantic_steps: [{ id: 'start', intent: 'Clarify the story', plain_inputs: [], plain_outputs: [] }],
  steps: [{ id: 'start', intent: 'Clarify the story' }], relationships: [], sources: [],
  pending_proposals: [], active_freezes: [], frozen_steps: [], history: [], blocked_findings: [],
  design_checks: { findings: [] }, generation_readiness: { ready: true, blocked_findings: [], compile_candidate: {} },
  ...overrides,
})
const response = (value: unknown) => Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } }))
let calls: { url: string; init?: RequestInit }[] = []

beforeEach(() => {
  localStorage.clear(); calls = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/ai-proposals')) return response({ proposal: { proposal_id: 'p1', revision: 1, summary: 'AI proposal', changes: [{ id: 'c1', target_id: 'start', operation: 'set_step_intent' }] } })
    if (url.includes('/preview')) return response({ impact: { plain_summary: 'One selected change.', changed_steps: ['start'], changed_sources: [] } })
    if (url.includes('/accept')) return response({ creator: creator({ revision: 2 }), accepted_change_ids: ['c1'] })
    if (url.includes('/runtime-handoff')) return response({ status: 'signed_handoff_ready', release_id: 'release-1', filename: 'handoff.zip', url: '/packages/handoff.zip', signature: { verified: true, key_id: 'creator' }, root_flow: { digest: 'sha256:test', protocol: { id: 'CF-FARP', version: '1.1' } } })
    if (url.includes('/compile-candidate')) return response({ compile_candidate: {} })
    return response({ creator: creator() })
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('creates a session through the creator API', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Creative intent'), { target: { value: 'Create a clear story' } })
  fireEvent.submit(screen.getByLabelText('Creative intent').closest('form')!)
  await screen.findByText('CartridgeFlow 创作工作室')
  expect(calls.some((call) => call.url.endsWith('/api/creator/authoring-sessions'))).toBe(true)
})

it('requests an AI proposal through the review endpoint', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  await screen.findByText('CartridgeFlow 创作工作室')
  fireEvent.change(screen.getByLabelText('Ask AI to modify the design'), { target: { value: 'Improve it' } })
  fireEvent.click(screen.getByLabelText('Request AI proposal'))
  await waitFor(() => expect(calls.some((call) => call.url.endsWith('/ai-proposals'))).toBe(true))
})

it('renders a signed handoff download after generation', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  await screen.findByText('CartridgeFlow 创作工作室')
  fireEvent.click(screen.getByLabelText('Generate handoff'))
  await screen.findByText(/release-1/)
  expect(screen.getByRole('link', { name: '下载 CF-CRE' })).toHaveAttribute('href', '/packages/handoff.zip')
})
