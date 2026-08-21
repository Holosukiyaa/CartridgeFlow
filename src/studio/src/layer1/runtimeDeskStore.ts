import { enqueueStudioJob, fetchStudioJob, type StudioRunJob } from '../api/client.ts'

type Listener = () => void

const listeners = new Set<Listener>()
const jobs = new Map<string, StudioRunJob>()
let blockingRunId: string | null = null
let toast: { id: string; title: string; detail: string } | null = null
let pollTimer = 0

function emit() {
  for (const listener of listeners) listener()
}

function activeStatuses(status: string) {
  return status === 'created' || status === 'running' || status === 'queued' || status === 'paused' || status === 'paused_waiting_user'
}

function startPolling() {
  if (pollTimer) return
  const tick = async () => {
    const pending = [...jobs.values()].filter((job) => activeStatuses(job.status) || job.active)
    if (!pending.length) {
      pollTimer = 0
      return
    }
    await Promise.all(pending.map(async (job) => {
      try {
        const next = await fetchStudioJob(job.run_id)
        const previous = jobs.get(job.run_id)
        jobs.set(next.run_id, next)
        if (previous && activeStatuses(previous.status) && !activeStatuses(next.status)) {
          const version = next.cartridge_version ? ` · v${next.cartridge_version}` : ''
          toast = {
            id: next.run_id,
            title: next.status === 'completed' ? '运行已完成' : '没有跑完',
            detail: next.status === 'completed'
              ? `${next.label || next.cartridge_id}${version}`
              : String(next.error?.cause_chain?.[0]?.message || next.error?.message || next.label || next.status),
          }
        }
      } catch {
        /* keep last snapshot */
      }
    }))
    emit()
    pollTimer = window.setTimeout(() => {
      pollTimer = 0
      startPolling()
    }, 800)
  }
  void tick()
}

export function subscribeRuntimeDesk(listener: Listener) {
  listeners.add(listener)
  return () => { listeners.delete(listener) }
}

export function getRuntimeDeskSnapshot() {
  return {
    jobs: [...jobs.values()].sort((a, b) => String(b.updated_at || b.created_at || '').localeCompare(String(a.updated_at || a.created_at || ''))),
    blockingRunId,
    toast,
  }
}

export function clearRuntimeToast() {
  toast = null
  emit()
}

export function setBlockingRun(runId: string | null) {
  blockingRunId = runId
  emit()
}

export async function startRuntimeJob(cartridgeId: string, inputs: Record<string, unknown>, label: string, projectId?: string) {
  const job = await enqueueStudioJob({ cartridge_id: cartridgeId, inputs, label, project_id: projectId })
  jobs.set(job.run_id, job)
  blockingRunId = job.run_id
  emit()
  startPolling()
  return job
}

export function rememberJobs(next: StudioRunJob[]) {
  for (const job of next) jobs.set(job.run_id, job)
  emit()
  if (next.some((job) => activeStatuses(job.status) || job.active)) startPolling()
}
