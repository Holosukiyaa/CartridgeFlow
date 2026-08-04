import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import App from './App'

const creator = (overrides = {}) => ({
  project_id: 'p1', session_id: 's1', revision: 1, intent: 'Create a clear story',
  semantic_steps: [{ id: 'start', intent: 'Clarify the story', plain_inputs: [], plain_outputs: [] }],
  steps: [{ id: 'start', intent: 'Clarify the story' }], relationships: [], sources: [],
  pending_proposals: [], active_freezes: [], frozen_steps: [], history: [], blocked_findings: [],
  design_checks: { findings: [] }, generation_readiness: { ready: true, blocked_findings: [], compile_candidate: {} },
  journey_graph: { project_id: 'p1', revision: 1, nodes: [{ id: 'project', kind: 'project', label: '项目', level: 0, status: 'active' }, { id: 'step:start', kind: 'recipe_step', label: 'Clarify the story', level: 1, status: 'review_needed' }, { id: 'engineering', kind: 'engineering', label: '工程验证', level: 2, status: 'ready' }], edges: [{ id: 'project-start', from: 'project', to: 'step:start', relation: 'contains' }, { id: 'start-engineering', from: 'step:start', to: 'engineering', relation: 'hands_off_to' }] },
  ...overrides,
})
const response = (value: unknown) => Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { 'Content-Type': 'application/json' } }))
let calls: { url: string; init?: RequestInit }[] = []

beforeEach(() => {
  localStorage.clear(); calls = []
  vi.stubGlobal('fetch', vi.fn((url: string, init?: RequestInit) => {
    calls.push({ url, init })
    if (url.endsWith('/possibilities')) return response({ possibilities: [{ id: 'signal-radar', title: '建立主题信号雷达', outcome: '每周获得重点变化。', why_it_fits: '适合先持续观察。', first_week_output: '一份摘要。', needs_confirmation: ['主题边界'], recipe: { intent: '持续跟踪：AI 行业', steps: [{ id: 'discover-sources', intent: '发现并审核相关公开来源', inputs: [], outputs: [] }] } }] })
    if (url.endsWith('/source-candidates')) return response({ candidates: [{ id: 'public-news', name: '公开行业观察', provides: '主题相关的公开报道。', why_recommended: '便于比较不同观点。', risk: '覆盖范围可能有限。', review_focus: '先确认最近内容是否匹配。', remote_url: 'https://example.test/', rss_url: '' }] })
    if (url.endsWith('/ai-proposals')) return response({ proposal: { proposal_id: 'p1', revision: 1, summary: 'AI proposal', changes: [{ id: 'c1', target_id: 'start', operation: 'set_step_intent' }] } })
    if (url.includes('/preview')) return response({ impact: { plain_summary: 'One selected change.', changed_steps: ['start'], changed_sources: [] } })
    if (url.includes('/accept')) return response({ creator: creator({ revision: 2 }), accepted_change_ids: ['c1'] })
    if (url.includes('/runtime-handoff')) return response({ status: 'signed_handoff_ready', release_id: 'release-1', filename: 'handoff.zip', url: '/packages/handoff.zip', signature: { verified: true, key_id: 'creator' }, root_flow: { digest: 'sha256:test', protocol: { id: 'CF-FARP', version: '1.1' } } })
    if (url.includes('/compile-candidate')) return response({ compile_candidate: {} })
    return response({ creator: creator() })
  }))
})
afterEach(() => { cleanup(); vi.unstubAllGlobals() })

  it('turns an open-ended thought into a selected creator recipe', async () => {
    render(<App />)
    fireEvent.change(screen.getByLabelText('Creative intent'), { target: { value: 'AI 行业' } })
    fireEvent.submit(screen.getByLabelText('Creative intent').closest('form')!)
    await screen.findAllByText('建立主题信号雷达')
    expect(screen.getByLabelText('Project journey graph')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: '选择这个方向' }))
    await waitFor(() => expect(calls.some((call) => call.url.endsWith('/api/creator/authoring-sessions'))).toBe(true))
    expect(calls.some((call) => call.url.endsWith('/api/creator/authoring-sessions'))).toBe(true)
  })

it('requests an AI proposal through the review endpoint', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  const prompt = await screen.findByLabelText('Ask AI to modify the design')
  fireEvent.change(prompt, { target: { value: 'Improve it' } })
  fireEvent.click(screen.getByLabelText('Request AI proposal'))
  await waitFor(() => expect(calls.some((call) => call.url.endsWith('/ai-proposals'))).toBe(true))
})

it('turns a source candidate into a reviewable source change', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  const request = await screen.findByLabelText('Discover source request')
  fireEvent.change(request, { target: { value: 'Find public reporting' } })
  fireEvent.click(screen.getByRole('button', { name: '寻找可审核来源' }))
  await screen.findAllByText('公开行业观察')
  expect(screen.getByLabelText('Project journey graph')).toBeInTheDocument()
  expect(screen.getByText(/覆盖范围可能有限/)).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: '纳入变更审阅' }))
  await waitFor(() => expect(calls.some((call) => call.url.endsWith('/proposals'))).toBe(true))
})

it('renders a signed handoff download after generation', async () => {
  localStorage.setItem('creator-session-id', 's1')
  render(<App />)
  fireEvent.click(await screen.findByLabelText('Generate handoff'))
  await screen.findByText(/release-1/)
  expect(screen.getByRole('link', { name: '下载 CF-CRE' })).toHaveAttribute('href', '/packages/handoff.zip')
})
