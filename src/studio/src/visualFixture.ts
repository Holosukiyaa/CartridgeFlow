import type { CreatorClarification, CreatorPossibility, CreatorRecipePreview } from './api/types.ts'
import type { StewardMessage } from './layer1/Steward.tsx'

export function visualFrame() {
  return new URLSearchParams(window.location.search).get('visual') || ''
}

export const FRAME1_MESSAGES: StewardMessage[] = [
  { id: 'visual.welcome', role: 'assistant', text: '点画布上的步骤告诉管家改哪里。按住 Shift 可以多选。' },
  { id: 'visual.user', role: 'user', text: '01先不要接邮件和IM，只从我审核过的公开RSS取当天内容。' },
]

export const FRAME1_PREVIEW: CreatorRecipePreview = {
  proposal_id: 'visual.preview',
  goal: '',
  nodes: [],
  relations: [],
  impact: { added_node_ids: [], removed_node_ids: [], retained_node_ids: ['1', '2', '3', '4', '5', '6', '7'] },
}

export const FRAME1_ERROR = '这次整体编排没有完成，请重试。输入还在，画布仍是旧七步。'

export const FRAME2_CLARIFY: CreatorClarification = {
  question: '这份日报必须从哪些你审核过的公开来源取内容？',
  why_it_matters: '来源名单决定第一步能不能补齐，不能默认去爬未审核网站。',
  suggested_answers: ['我常用的科技RSS列表', '我指定的几个网站', '先用公开AI新闻源，我之后再改'],
}

export const FRAME2_DIRECTIONS: CreatorPossibility[] = [
  {
    id: 'd1',
    title: '来源审核型早报',
    outcome: '先锁定来源，再筛重点、写中文草稿、你确认后交付',
    why_it_fits: '适合你强调来源必须先经过审核',
    first_week_output: '',
    needs_confirmation: [],
    recipe: { intent: '来源审核型早报', steps: [] },
  },
  {
    id: 'd2',
    title: '要点优先型简报',
    outcome: '先按主题筛，来源作为附录',
    why_it_fits: '适合想更快读到结论的场景',
    first_week_output: '',
    needs_confirmation: [],
    recipe: { intent: '要点优先型简报', steps: [] },
  },
  {
    id: 'd3',
    title: '人工确认后固化',
    outcome: '简报必须你点头才能保存和交付',
    why_it_fits: '适合对所有输出都需要人工把关的工作流',
    first_week_output: '',
    needs_confirmation: [],
    recipe: { intent: '人工确认后固化', steps: [] },
  },
]
