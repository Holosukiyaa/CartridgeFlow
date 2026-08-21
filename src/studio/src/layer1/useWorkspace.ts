import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  ApiError,
  deleteCreatorProject,
  composeCreatorRecipe,
  connectCreatorAi,
  deliverCreatorProject,
  discoverCreatorPossibilities,
  fetchCreatorAiStatus,
  fetchCreatorProject,
  fetchCreatorWorkspace,
  fetchDesktopRunnerStatus,
  listCreatorProjects,
  renameCreatorProject,
  fetchCreatorSession,
  packageCreatorProject,
  previewCreatorRecompose,
  acceptCreatorRecompose,
  refineCreatorNodeWithAi,
  resolveCreatorCapabilities,
  saveCreatorWorkspace,
  type CreatorClarification,
  type CreatorPackage,
  type CreatorPossibility,
  type CreatorProjection,
  type CreatorRecipePreview,
  type CreatorRunnerDelivery,
  type DesktopRunnerStatus,
} from '../api/client.ts'
import { COMPOSE_INPUT_ID, MIN_GOAL_LENGTH, NARROW_QUERY, RUNNER_FALLBACK_URL, SAVE_DEBOUNCE_MS, type ShellTabId } from '../config.ts'
import { copy } from '../copy.ts'
import { clearWorkshopReturn, nextUnconfirmed, resolveGuidance, reviewCounts, workshopReturnFromLocation, type WorkspaceSnapshot } from './model.ts'
import { createDraftProjectId, projectStudioPath, readSnapshot, rememberProjectId, writeSnapshot } from './persistence.ts'
import type { StewardMessage, StewardScope } from './Steward.tsx'
import { useMedia } from './useMedia.ts'

type SyncIssue =
  | { kind: 'load' }
  | { kind: 'save'; snapshot: WorkspaceSnapshot; expectedRevision: number }
  | { kind: 'conflict'; snapshot: WorkspaceSnapshot }

export function useWorkspace(projectId: string) {
  const restored = useMemo(() => readSnapshot(projectId), [projectId])
  const [creator, setCreator] = useState<CreatorProjection | null>(null)
  const [goal, setGoal] = useState(restored?.goal || '')
  const [selectedId, setSelectedId] = useState(restored?.selectedId || '')
  const [clarification, setClarification] = useState<CreatorClarification | null>(restored?.clarification || null)
  const [possibilities, setPossibilities] = useState<CreatorPossibility[]>(restored?.possibilities || [])
  const [input, setInput] = useState('')
  const [messages, setMessages] = useState<StewardMessage[]>(restored?.messages || [])
  const [recipePreview, setRecipePreview] = useState<CreatorRecipePreview | null>(null)
  const [stewardScope, setStewardScope] = useState<StewardScope>('recipe')
  const [stewardOpen, setStewardOpen] = useState(false)
  const [contextIds, setContextIds] = useState<string[]>([])
  const [layer2Flows, setLayer2Flows] = useState<Record<string, string>>(restored?.layer2Flows || {})
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(true)
  const [connectOpen, setConnectOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [returnedFromWorkshop, setReturnedFromWorkshop] = useState(false)
  const [layer2NodeId, setLayer2NodeId] = useState('')
  const [detailOpen, setDetailOpen] = useState(false)
  const [tab, setTab] = useState<ShellTabId>('canvas')
  const [projectMenuOpen, setProjectMenuOpen] = useState(false)
  const [projects, setProjects] = useState<Array<{ project_id: string; name: string; revision: number }>>([])
  const [aiStatus, setAiStatus] = useState({ provider: '', has_key: false, base_url: '', model: '' })
  const [packageResult, setPackageResult] = useState<CreatorPackage | null>(restored?.packageResult || null)
  const [packageRevision, setPackageRevision] = useState<number | null>(restored?.packageRevision || null)
  const [packageError, setPackageError] = useState('')
  const [runnerStatus, setRunnerStatus] = useState<DesktopRunnerStatus | null>(null)
  const [runnerDelivery, setRunnerDelivery] = useState<CreatorRunnerDelivery | null>(null)
  const [syncLabel, setSyncLabel] = useState('尚未开始')
  const [syncIssue, setSyncIssue] = useState<SyncIssue | null>(null)
  const [syncWorking, setSyncWorking] = useState(false)
  const [loadAttempt, setLoadAttempt] = useState(0)
  const connectedRef = useRef<boolean | null>(false)
  const revisionRef = useRef(0)
  const saveRequestRef = useRef(0)
  const hydratedRef = useRef(false)
  const syncIssueRef = useRef<SyncIssue | null>(null)
  const runtimeInputsRef = useRef(restored?.runtimeInputs || {})
  const narrow = useMedia(NARROW_QUERY)
  const updateSyncIssue = useCallback((issue: SyncIssue | null) => {
    syncIssueRef.current = issue
    setSyncIssue(issue)
  }, [])
  const applySnapshot = useCallback((snapshot: WorkspaceSnapshot) => {
    setGoal(snapshot.goal)
    setClarification(snapshot.clarification)
    setPossibilities(snapshot.possibilities)
    setSelectedId(snapshot.selectedId)
    setPackageResult(snapshot.packageResult)
    setPackageRevision(snapshot.packageRevision)
    setMessages(snapshot.messages || [])
    setLayer2Flows(snapshot.layer2Flows || {})
    runtimeInputsRef.current = snapshot.runtimeInputs || {}
  }, [])
  const saveSnapshot = useCallback(async (snapshot: WorkspaceSnapshot, expectedRevision: number) => {
    const requestId = ++saveRequestRef.current
    setSyncLabel('正在保存草稿')
    try {
      const { workspace } = await saveCreatorWorkspace(projectId, snapshot, expectedRevision)
      revisionRef.current = workspace.revision
      if (requestId !== saveRequestRef.current) return true
      updateSyncIssue(null)
      setSyncLabel('草稿已保存')
      return true
    } catch (reason) {
      if (requestId !== saveRequestRef.current) return false
      if (reason instanceof ApiError && reason.code.includes('REVISION_CONFLICT')) {
        updateSyncIssue({ kind: 'conflict', snapshot })
        setSyncLabel('REVISION_CONFLICT')
      } else {
        updateSyncIssue({ kind: 'save', snapshot, expectedRevision })
        setSyncLabel('同步失败')
      }
      return false
    }
  }, [projectId, updateSyncIssue])
  const refreshProjects = useCallback(async () => {
    const result = await listCreatorProjects()
    setProjects(result.projects)
    return result.projects
  }, [])

  useEffect(() => {
    const snapshot: WorkspaceSnapshot = {
      version: 1,
      goal,
      messages,
      clarification,
      possibilities,
      selectedId,
      packageResult,
      packageRevision,
      layer2Flows,
      runtimeInputs: runtimeInputsRef.current,
    }
    writeSnapshot(projectId, snapshot)
    if (!hydratedRef.current) return
    setSyncLabel('正在保存草稿')
    const timer = window.setTimeout(() => {
      if (!hydratedRef.current) return
      void saveSnapshot(snapshot, revisionRef.current)
    }, SAVE_DEBOUNCE_MS)
    return () => window.clearTimeout(timer)
  }, [clarification, goal, layer2Flows, messages, packageResult, packageRevision, possibilities, projectId, saveSnapshot, selectedId])

  useEffect(() => {
    let active = true
    Promise.all([fetchCreatorProject(projectId), fetchCreatorWorkspace<WorkspaceSnapshot>(projectId)])
      .then(async ([{ creator: value }, { workspace }]) => {
        if (!active) return
        const recovered = workspace?.snapshot || restored
        revisionRef.current = workspace?.revision || 0
        hydratedRef.current = true
        if (recovered) applySnapshot(recovered)
        if (!value) {
          setSyncLabel('等待连接 AI')
          return
        }
        const returned = workshopReturnFromLocation()
        let next = value
        if (returned.published) {
          try {
            const resolved = await resolveCreatorCapabilities(value.session_id, value.revision)
            next = resolved.creator
          } catch {
            next = value
          }
        }
        if (!active) return
        setCreator(next)
        setGoal(next.intent)
        const fallback = nextUnconfirmed(next)?.id || next.trusted_recipe.nodes[0]?.id || ''
        const selected = next.trusted_recipe.nodes.some((node) => node.id === returned.nodeId)
          ? returned.nodeId
          : recovered?.selectedId && next.trusted_recipe.nodes.some((node) => node.id === recovered.selectedId)
            ? recovered.selectedId
            : fallback
        setSelectedId(selected)
        if (selected) {
          setContextIds([selected])
          setStewardScope('node')
          setDetailOpen(true)
        }
        if (returned.nodeId && next.trusted_recipe.nodes.some((node) => node.id === returned.nodeId)) {
          setDetailOpen(true)
          setTab('detail')
          setReturnedFromWorkshop(Boolean(returned.published))
        }
        if (returned.published || returned.nodeId) clearWorkshopReturn()
        if (recovered?.packageRevision !== next.revision) {
          setPackageResult(null)
          setPackageRevision(null)
          setRunnerDelivery(null)
        }
        setSyncLabel(returned.published ? copy.returnedFromWorkshop : '草稿已保存')
      })
      .catch(() => {
        if (!active) return
        updateSyncIssue({ kind: 'load' })
        setSyncLabel('草稿读取失败')
      })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [applySnapshot, loadAttempt, projectId, restored, updateSyncIssue])

  useEffect(() => {
    void refreshProjects().catch(() => null)
  }, [projectId, creator?.revision, refreshProjects])

  useEffect(() => {
    fetchCreatorAiStatus().then((status) => {
      setAiStatus(status)
      connectedRef.current = status.has_key
      if (!status.has_key && !syncIssueRef.current) setSyncLabel('等待连接 AI')
    }).catch(() => null)
    fetchDesktopRunnerStatus().then(setRunnerStatus).catch(() => null)
  }, [])

  const selectedNode = creator?.trusted_recipe.nodes.find((node) => node.id === selectedId) || null
  const contextNodes = creator?.trusted_recipe.nodes.filter((node) => contextIds.includes(node.id)) || []
  const layer2Node = creator?.trusted_recipe.nodes.find((node) => node.id === layer2NodeId) || null
  const guidance = useMemo(
    () => resolveGuidance({ creator, clarification, possibilities, packageResult, connected: aiStatus.has_key, runnerStatus, runnerDelivery }),
    [aiStatus.has_key, clarification, creator, packageResult, possibilities, runnerDelivery, runnerStatus],
  )
  const stats = creator ? reviewCounts(creator) : null

  const saveCreator = (next: CreatorProjection) => {
    setCreator(next)
    setPackageResult(null)
    setPackageRevision(null)
    setPackageError('')
    setRunnerDelivery(null)
    setSyncLabel('草稿已保存')
  }

  const startNewProject = () => {
    const nextProjectId = createDraftProjectId()
    rememberProjectId(nextProjectId)
    window.location.assign(projectStudioPath(nextProjectId))
  }

  const renameProject = async (name: string) => {
    const normalized = name.trim()
    if (!normalized) return
    setBusy(true)
    setError('')
    try {
      const result = await renameCreatorProject(projectId, normalized)
      saveCreator(result.creator)
      void refreshProjects().catch(() => null)
      setProjectMenuOpen(false)
    } catch {
      setError(copy.projectActionFail)
      throw new Error(copy.projectActionFail)
    } finally {
      setBusy(false)
    }
  }

  const deleteProject = async () => {
    setBusy(true)
    setError('')
    hydratedRef.current = false
    try {
      await deleteCreatorProject(projectId)
      const remaining = await refreshProjects().catch(() => projects.filter((project) => project.project_id !== projectId))
      const nextProjectId = remaining.find((project) => project.project_id !== projectId)?.project_id || ''
      rememberProjectId(nextProjectId)
      window.location.assign(nextProjectId ? projectStudioPath(nextProjectId) : '/studio')
    } catch {
      hydratedRef.current = true
      setError(copy.projectActionFail)
      throw new Error(copy.projectActionFail)
    } finally {
      setBusy(false)
    }
  }

  const requireModel = () => { setConnectOpen(true) }

  const pushMessage = (role: 'assistant' | 'user', text: string) => {
    setMessages((current) => [...current.slice(-79), { id: `${role}.${Date.now()}`, role, text }])
  }

  const discover = async (context = goal || input, visible = context) => {
    const text = context.trim()
    if (text.length < MIN_GOAL_LENGTH) return
    if (connectedRef.current === false) return requireModel()
    setBusy(true)
    setError('')
    setPossibilities([])
    setClarification(null)
    setGoal(text)
    try {
      const discovery = await discoverCreatorPossibilities(visible.trim())
      setPossibilities(discovery.possibilities)
      setClarification(discovery.clarification)
      setInput('')
      pushMessage('assistant', discovery.clarification
        ? discovery.clarification.question
        : `我整理了 ${discovery.possibilities.length} 个可比较方向。选一个之后才会生成大纲。`)
    } catch (reason) {
      if (reason instanceof ApiError && reason.code.includes('MODEL_UNBOUND')) return requireModel()
      setError(reason instanceof ApiError && reason.code.includes('TIMEOUT') ? copy.timeout : copy.discoverFail)
    } finally { setBusy(false) }
  }

  const compose = async (nextGoal: string) => {
    if (nextGoal.trim().length < MIN_GOAL_LENGTH) return
    if (connectedRef.current === false) return requireModel()
    setBusy(true)
    setError('')
    setPossibilities([])
    setClarification(null)
    try {
      const result = await composeCreatorRecipe({ session_id: `creator.${crypto.randomUUID()}`, project_id: projectId, goal: nextGoal.trim() })
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setSelectedId(result.creator.trusted_recipe.nodes[0]?.id || '')
      setStewardOpen(false)
      pushMessage('assistant', '第一版大纲已经在画布上。继续说哪里不对，或点拼图进入某一步的内部做法。')
    } catch (reason) {
      if (reason instanceof ApiError && reason.code.includes('MODEL_UNBOUND')) return requireModel()
      setError(copy.composeFail)
    } finally { setBusy(false) }
  }

  const submitComposer = () => {
    const text = input.trim()
    if (!text) return
    if (creator) return void talkToSteward()
    pushMessage('user', text)
    if (clarification) {
      setClarification(null)
      void discover(`${goal.trim()}\n补充：${text}`, text)
      return
    }
    void discover(text)
  }

  const talkToSteward = async () => {
    const text = input.trim()
    if (!text || !creator) return
    if (connectedRef.current === false) return requireModel()
    setInput('')
    pushMessage('user', text)
    setBusy(true)
    setError('')
    try {
      const focused = contextIds
        .map((id) => creator.trusted_recipe.nodes.find((node) => node.id === id))
        .filter((node): node is NonNullable<typeof node> => Boolean(node))
      if (stewardScope === 'node' && focused.length === 1) {
        const target = focused[0]
        const result = await refineCreatorNodeWithAi(creator.session_id, target.id, {
          prompt: text, expected_revision: creator.revision, author: 'creator', summary: `调整 ${target.label}`,
        })
        const session = await fetchCreatorSession(creator.session_id)
        saveCreator(session.creator)
        setDetailOpen(true)
        setTab('detail')
        pushMessage('assistant', result.proposal.summary || `已为「${target.label}」准备建议，请在详情里应用或放弃。`)
        return
      }
      const scopeLine = focused.length ? `本轮只讨论这些步骤：${focused.map((node) => `「${node.label}」`).join('、')}。\n` : ''
      const nextGoal = `${creator.intent}\n${scopeLine}本轮补充：${text}`
      const preview = await previewCreatorRecompose(creator.session_id, { goal: nextGoal, expected_revision: creator.revision })
      setRecipePreview(preview)
      setGoal(nextGoal)
      pushMessage('assistant', '我把这一轮补充做成了新大纲预览。先看变化，再决定用不用。')
    } catch (reason) {
      if (reason instanceof ApiError && reason.code.includes('MODEL_UNBOUND')) return requireModel()
      setError(reason instanceof ApiError && reason.code.includes('TIMEOUT') ? copy.timeout : copy.composeFail)
    } finally { setBusy(false) }
  }

  const applyRecipePreview = async () => {
    if (!creator || !recipePreview) return
    setBusy(true)
    setError('')
    try {
      const result = await acceptCreatorRecompose(creator.session_id, recipePreview.proposal_id, creator.revision)
      saveCreator(result.creator)
      setGoal(result.creator.intent)
      setRecipePreview(null)
      pushMessage('assistant', '这版已经应用到画布。继续指出不对的地方。')
    } catch (reason) {
      if (reason instanceof ApiError && reason.code.includes('MODEL_UNBOUND')) return requireModel()
      setError(copy.composeFail)
    } finally { setBusy(false) }
  }

  const rejectRecipePreview = () => {
    setRecipePreview(null)
    if (creator) setGoal(creator.intent)
    pushMessage('assistant', '这版先不用。画布还是原来的大纲。')
  }

  const buildPackage = async () => {
    if (!creator) return null
    setBusy(true)
    setPackageError('')
    try {
      const result = await packageCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result)
      setPackageRevision(creator.revision)
      setRunnerDelivery(null)
      return result
    } catch (reason) {
      const message = reason instanceof ApiError
        ? (reason.message && reason.message !== 'Creator service is unavailable.' ? reason.message : copy.packageBlocked)
        : copy.packageFail
      setPackageError(message)
      throw new Error(message)
    } finally { setBusy(false) }
  }

  const deliver = async () => {
    if (!creator || !packageResult) return
    setBusy(true)
    try {
      const result = await deliverCreatorProject(creator.session_id, creator.revision)
      setPackageResult(result.package)
      setRunnerDelivery(result)
    } catch {
      setPackageError(copy.runnerFail)
    } finally { setBusy(false) }
  }

  const openNode = (nodeId: string) => {
    setSelectedId(nodeId)
    setContextIds([nodeId])
    setDetailOpen(true)
    setTab('detail')
  }

  const rememberLayer2 = useCallback((nodeId: string, flowId: string) => {
    setLayer2Flows((current) => current[nodeId] === flowId ? current : { ...current, [nodeId]: flowId })
  }, [])

  const openLayer2 = useCallback((nodeId: string) => {
    setSelectedId(nodeId)
    setDetailOpen(true)
    setTab('detail')
    setLayer2NodeId(nodeId)
  }, [])

  const closeLayer2 = useCallback(() => {
    setLayer2NodeId('')
  }, [])

  const finishLayer2 = useCallback(async (nodeId: string, published: boolean) => {
    if (published && creator) {
      try {
        const resolved = await resolveCreatorCapabilities(creator.session_id, creator.revision)
        setCreator(resolved.creator)
        setPackageResult(null)
        setPackageRevision(null)
        setPackageError('')
        setRunnerDelivery(null)
        setReturnedFromWorkshop(true)
        setSyncLabel(copy.returnedFromWorkshop)
      } catch {
        setSyncLabel(copy.returnedFromWorkshop)
      }
    }
    setSelectedId(nodeId)
    setDetailOpen(true)
    setTab('detail')
    setLayer2NodeId('')
  }, [creator])

  const closeDetail = () => {
    setDetailOpen(false)
    setTab('canvas')
  }

  const retrySync = async () => {
    if (!syncIssue || syncWorking) return
    if (syncIssue.kind === 'load') {
      updateSyncIssue(null)
      setLoading(true)
      setLoadAttempt((current) => current + 1)
      return
    }
    setSyncWorking(true)
    try {
      if (syncIssue.kind === 'save') {
        await saveSnapshot(syncIssue.snapshot, syncIssue.expectedRevision)
        return
      }
      setSyncLabel('正在确认服务端版本')
      try {
        const { workspace } = await fetchCreatorWorkspace<WorkspaceSnapshot>(projectId)
        await saveSnapshot(syncIssue.snapshot, workspace?.revision || 0)
      } catch {
        setSyncLabel('同步失败')
      }
    } finally {
      setSyncWorking(false)
    }
  }

  const reloadServerDraft = async () => {
    if (syncIssue?.kind !== 'conflict' || syncWorking) return
    setSyncWorking(true)
    setSyncLabel('正在读取服务端草稿')
    try {
      const { workspace } = await fetchCreatorWorkspace<WorkspaceSnapshot>(projectId)
      if (!workspace) {
        setSyncLabel('草稿读取失败')
        return
      }
      revisionRef.current = workspace.revision
      applySnapshot(workspace.snapshot)
      updateSyncIssue(null)
      setSyncLabel('已加载服务端草稿')
    } catch {
      setSyncLabel('草稿读取失败')
    } finally {
      setSyncWorking(false)
    }
  }

  const runPrimaryAction = () => {
    if (guidance.action === 'connect') return requireModel()
    if (guidance.action === 'compose') {
      document.getElementById(COMPOSE_INPUT_ID)?.focus()
      return
    }
    if (guidance.action === 'open-node' && guidance.nodeId) return openNode(guidance.nodeId)
    if (guidance.action === 'package') return void buildPackage()
    if (guidance.action === 'deliver') return void deliver()
    if (guidance.action === 'runner') {
      window.open(runnerDelivery?.delivery.runner_url || runnerStatus?.url || RUNNER_FALLBACK_URL, '_blank', 'noopener,noreferrer')
      return
    }
    if (guidance.action === 'download' && packageResult) {
      const link = document.createElement('a')
      link.href = packageResult.url
      link.download = packageResult.filename
      link.click()
    }
  }

  return {
    projectId,
    creator,
    goal,
    selectedId,
    selectedNode,
    contextNodes,
    clarification,
    possibilities,
    input,
    messages,
    recipePreview,
    stewardScope,
    stewardOpen,
    error,
    busy,
    loading,
    connectOpen,
    settingsOpen,
    returnedFromWorkshop,
    layer2Node,
    detailOpen,
    tab,
    narrow,
    projectMenuOpen,
    projects,
    startNewProject,
    renameProject,
    deleteProject,
    aiStatus,
    packageResult,
    packageError,
    buildPackage,
    runnerDelivery,
    syncLabel: busy ? copy.processing : syncLabel,
    syncIssue: syncIssue?.kind || null,
    syncWorking,
    retrySync,
    reloadServerDraft,
    guidance,
    stats,
    showDetail: Boolean(detailOpen && selectedNode && creator),
    projectName: creator?.short_name || creator?.project_name || creator?.intent || projects.find((project) => project.project_id === projectId)?.name || copy.unnamedProject,
    connectionLabel: aiStatus.has_key ? (aiStatus.model || copy.connected) : copy.disconnected,
    connected: aiStatus.has_key,
    setInput: (value: string) => { setInput(value); setError('') },
    setStewardScope,
    setStewardOpen,
    setConnectOpen,
    setSettingsOpen,
    setProjectMenuOpen,
    setTab: (next: ShellTabId) => { setTab(next); if (next === 'detail') setDetailOpen(true) },
    openNode,
    openLayer2,
    closeLayer2,
    finishLayer2,
    closeDetail,
    selectCanvasNode: (nodeId: string, additive = false) => {
      if (!nodeId) {
        setContextIds([])
        closeDetail()
        return
      }
      if (additive) {
        setSelectedId(nodeId)
        setContextIds((current) => current.includes(nodeId) ? current.filter((id) => id !== nodeId) : [...current, nodeId])
        return
      }
      openNode(nodeId)
    },
    rememberLayer2,
    contextIds,
    layer2Flows,
    clearContext: () => setContextIds([]),
    removeContext: (nodeId: string) => setContextIds((current) => current.filter((id) => id !== nodeId)),
    submitComposer,
    talkToSteward,
    applyRecipePreview,
    rejectRecipePreview,
    clarify: (answer: string) => { pushMessage('user', answer); setClarification(null); void discover(`${goal.trim()}\n补充：${answer}`, answer) },
    chooseDirection: (intent: string) => { pushMessage('user', `采用方向：${intent}`); setGoal(intent); setPossibilities([]); void compose(intent) },
    skipDirections: () => { setPossibilities([]); requestAnimationFrame(() => document.getElementById(COMPOSE_INPUT_ID)?.focus()) },
    retryDiscover: () => { setError(''); if (goal.trim()) void discover(goal) },
    runPrimaryAction,
    requireModel,
    saveCreator: (next: CreatorProjection) => {
      saveCreator(next)
      const following = nextUnconfirmed(next)
      if (following && following.id !== selectedNode?.id) setSelectedId(following.id)
    },
    connect: async (connection: { base_url: string; api_key: string; model: string }) => {
      await connectCreatorAi(connection)
      connectedRef.current = true
      const status = await fetchCreatorAiStatus().catch(() => null)
      if (status) setAiStatus(status)
      setConnectOpen(false)
      setSyncLabel('等待目标描述')
    },
  }
}
