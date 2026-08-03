import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import App from './App'

const creator = (overrides = {}) => ({ session_id: 's1', revision: 1, intent: 'Summarize declared information', semantic_steps: [{ id: 'start', intent: 'Begin the work', plain_inputs: [], plain_outputs: [] }], steps: [{ id: 'start', intent: 'Begin the work' }], relationships: [], sources: [], pending_proposals: [], active_freezes: [], frozen_steps: [], history: [], blocked_findings: [{ code: 'DESIGN_STEP_UNFROZEN', severity: 'blocked', step_id: 'start', message: 'This design step is not frozen.' }], design_checks: { findings: [] }, generation_readiness: { ready: false, blocked_findings: [], compile_candidate: null }, ...overrides })
const json = (body: unknown, status = 200) => Promise.resolve(new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } }))
let calls: { url: string; init?: RequestInit }[] = []
const recorded = () => (vi.mocked(fetch).mock.calls.map(([url, init]) => ({ url: String(url), init: init as RequestInit })))
beforeEach(() => { localStorage.clear(); calls = []; vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => { calls.push({ url, init }); return json({ creator: creator() }) })) })
afterEach(() => { cleanup(); vi.unstubAllGlobals() })
const bodyAt = (part: string) => JSON.parse(String(recorded().find(call => call.url.includes(part))?.init?.body || '{}'))

it('creates a session through HTTP and renders its projection', async () => {
  ;(fetch as ReturnType<typeof vi.fn>).mockImplementationOnce(() => json({ creator: creator() }))
  render(<App />); fireEvent.change(screen.getByLabelText('Creative intent'), { target: { value: 'Summarize declared information' } }); fireEvent.click(screen.getByRole('button', { name: 'Create authoring session' }))
  await screen.findByText('Sources'); expect(recorded()[0].url).toContain('/api/creator/authoring-sessions'); expect(recorded()[0].init?.method).toBe('POST'); expect(bodyAt('authoring-sessions').steps[0].id).toBe('start')
})

it('loads a stored session and runs source proposal preview acceptance', async () => {
  localStorage.setItem('creator-session-id', 's1')
  ;(fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => url.endsWith('/s1') ? json({ creator: creator() }) : url.endsWith('/proposals') ? json({ proposal: { proposal_id: 'p1', revision: 1, summary: 'Add', changes: [{ id: 'c1', target_id: 'source-1', operation: 'add_source' }] } }) : url.includes('/preview') ? json({ accepted_change_ids: ['c1'] }) : json({ creator: creator({ sources: [{ id: 'source-1', kind: 'source', digest: '0'.repeat(64), remote_url: 'https://example.com' }] }), accepted_change_ids: ['c1'] }))
  render(<App />); await screen.findByText('Sources'); fireEvent.change(screen.getByLabelText('Add source URL'), { target: { value: 'https://example.com' } }); fireEvent.click(screen.getByRole('button', { name: 'Propose source' }))
  await waitFor(() => expect(recorded().some(call => call.url.includes('/preview'))).toBe(true)); expect(bodyAt('/proposals').changes[0].operation).toBe('add_source'); expect(bodyAt('/proposals').changes[0].value.remote_url).toBe('https://example.com/')
})

it('does not send unsafe source values', async () => { localStorage.setItem('creator-session-id', 's1'); render(<App />); await screen.findByText('Sources'); fireEvent.change(screen.getByLabelText('Add source URL'), { target: { value: 'https://user:pass@example.com/?token=no' } }); fireEvent.click(screen.getByRole('button', { name: 'Propose source' })); expect(screen.getByRole('status')).toHaveTextContent('credential-free HTTPS'); expect(recorded()).toHaveLength(1) })

it('reviews an AI proposal, partially accepts exact selected ids, and rejects proposals', async () => {
  localStorage.setItem('creator-session-id', 's1'); const proposal = { proposal_id: 'p-ai', revision: 1, summary: 'AI proposal', changes: [{ id: 'a', target_id: 'start', operation: 'set_step_intent' }, { id: 'b', target_id: 'start', operation: 'set_step_intent' }] }
  ;(fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => url.endsWith('/s1') ? json({ creator: creator() }) : url.endsWith('/ai-proposals') ? json({ proposal }) : url.includes('/preview') ? json({ accepted_change_ids: ['a'] }) : url.includes('/accept') ? json({ creator: creator({ revision: 2 }), accepted_change_ids: ['a'] }) : json({ creator: creator() }))
  render(<App />); await screen.findByText('Sources'); fireEvent.change(screen.getByLabelText('Ask AI to modify the design'), { target: { value: 'Make it clearer' } }); fireEvent.click(screen.getByRole('button', { name: 'Ask AI' })); await screen.findByText('AI proposal'); fireEvent.click(screen.getAllByLabelText(/set_step_intent start/)[1]); fireEvent.click(screen.getByRole('button', { name: 'Accept selected (1)' })); await waitFor(() => expect(bodyAt('/accept').selected_change_ids).toEqual(['a'])); expect(screen.getByRole('status')).toHaveTextContent('Accepted 1 of 1')
})

it('includes an active freeze revision on frozen canvas edits and reports reversal conflicts', async () => {
  localStorage.setItem('creator-session-id', 's1'); const frozen = creator({ frozen_steps: ['start'], active_freezes: [{ id: 'f1', steps: ['start'], freeze_revision: { source_freeze_ids: ['f1'], expected_revision: 1 } }], history: [{ id: 'a1', revision: 1, summary: 'Old change' }] })
  ;(fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => url.endsWith('/s1') ? json({ creator: frozen }) : url.endsWith('/proposals') ? json({ proposal: { proposal_id: 'p1', revision: 1, summary: 'edit', changes: [{ id: 'c1', target_id: 'start', operation: 'set_step_intent' }] } }) : url.includes('/preview') ? json({ accepted_change_ids: ['c1'] }) : url.includes('/accept') ? json({ creator: frozen, accepted_change_ids: ['c1'] }) : url.includes('/reverse') ? json({ detail: { code: 'AUTHORING_REVERSAL_AMBIGUOUS', message: 'Cannot reverse safely.' } }, 409) : json({ creator: frozen }))
  render(<App />); await screen.findByText('Begin the work'); fireEvent.click(screen.getByRole('button', { name: 'Edit' })); await waitFor(() => expect(bodyAt('/preview').freeze_revision.source_freeze_ids).toEqual(['f1'])); fireEvent.click(screen.getByRole('button', { name: 'Reverse' })); await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent('AUTHORING_REVERSAL_AMBIGUOUS'))
})

it('checks readiness and only compiles a ready handoff candidate', async () => {
  localStorage.setItem('creator-session-id', 's1'); const ready = creator({ generation_readiness: { ready: true, blocked_findings: [], compile_candidate: {} }, blocked_findings: [] })
  ;(fetch as ReturnType<typeof vi.fn>).mockImplementation((url: string) => url.endsWith('/s1') ? json({ creator: ready }) : url.endsWith('/design-checks') ? json({ design_checks: { findings: [] } }) : url.endsWith('/generation-readiness') ? json({ generation_readiness: ready.generation_readiness }) : json({ compile_candidate: { id: 'compile-1' } }))
  render(<App />); await screen.findByText('Create handoff candidate'); fireEvent.click(screen.getByRole('button', { name: 'Run design check' })); fireEvent.click(screen.getByRole('button', { name: 'Check readiness' })); fireEvent.click(screen.getByRole('button', { name: 'Create handoff candidate' })); await waitFor(() => expect(recorded().some(call => call.url.includes('/compile-candidate'))).toBe(true)); expect(bodyAt('/compile-candidate').expected_revision).toBe(1)
})
