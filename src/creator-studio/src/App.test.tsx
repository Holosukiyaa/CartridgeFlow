import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

const creator = (overrides = {}) => ({
  project_id: 'p1', session_id: 's1', revision: 1, intent: '制作 AI 日报',
  trusted_recipe: {
    id: 'recipe.s1', goal: '制作 AI 日报',
    nodes: [{ id: 'sources', label: '收集可信来源', preset: { id: 'rss-source', revision: 2, digest: 'sha256:test' }, values: { topics: ['AI'] }, editable_fields: [{ id: 'topics', label: '关注主题', value_type: 'string_list', required: true, default: ['AI'] }] }],
    relations: [],
  },
  frozen_steps: [], pending_proposals: [], history: [], blocked_findings: [{ code: 'DESIGN_STEP_UNFROZEN', severity: 'blocked', step_id: 'sources', message: 'This design step is not frozen.' }],
  generation_readiness: { ready: false, blocked_findings: [] },
  journey_graph: { project_id: 'p1', revision: 1, nodes: [], edges: [] },
  ...overrides,
})
const response = (value: unknown) => Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } }))
let calls: { url: string; init?: RequestInit }[] = []

beforeEach(() => {
  localStorage.clear(); history.replaceState({}, '', '/'); calls = []
  vi.stubGlobal('crypto', { randomUUID: () => 'test-id' })
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/compose-recipe')) return response({ creator: creator() })
    if (url.includes('/nodes/sources/ai-proposals')) return response({ proposal: { proposal_id: 'proposal-1', revision: 1, summary: '深化来源', changes: [{ id: 'refine.sources.1', target_id: 'sources', operation: 'set_creator_binding' }] } })
    if (url.includes('/preview')) return response({ accepted_change_ids: ['refine.sources.1'], impact: { plain_summary: '只影响收集可信来源节点。' } })
    return response({ creator: creator() })
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('composes the empty canvas through the trusted recipe endpoint', async () => {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Creative intent'), { target: { value: '制作 AI 日报' } })
  fireEvent.submit(screen.getByLabelText('Creative intent').closest('form')!)
  await screen.findByText('整体草稿已生成，请逐个审核节点。')
  expect(calls.some((call) => call.url.endsWith('/compose-recipe'))).toBe(true)
  expect(screen.getAllByText('收集可信来源')).toHaveLength(2)
})

it('deepens only the selected trusted node through its scoped endpoint', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  fireEvent.click((await screen.findAllByRole('button', { name: /收集可信来源/ }))[1])
  fireEvent.change(screen.getByLabelText('Node refinement request'), { target: { value: '增加三个可靠来源类别' } })
  fireEvent.click(screen.getByLabelText('Request node AI proposal'))
  await waitFor(() => expect(calls.some((call) => call.url.includes('/nodes/sources/ai-proposals'))).toBe(true))
  expect(await screen.findByText('深化来源')).toBeInTheDocument()
})

it('shows a capability gap instead of inventing an unmapped node', async () => {
  vi.mocked(fetch).mockImplementationOnce((url: string | URL | Request) => { calls.push({ url: String(url) }); return response({ capability_gap: { schema: 'cartridgeflow.creator_capability_gap.v1', goal: '未知能力', needed_capabilities: ['需要新的可信采集能力'], available_preset_ids: [] } }) })
  render(<App />)
  fireEvent.change(screen.getByLabelText('Creative intent'), { target: { value: '未知能力' } })
  fireEvent.submit(screen.getByLabelText('Creative intent').closest('form')!)
  expect(await screen.findByText('需要新的可信采集能力')).toBeInTheDocument()
  expect(screen.queryByText('整体草稿')).not.toBeInTheDocument()
})
