import { useEffect, useRef, useState } from 'react'
import { fetchInteractionSandbox, revokeInteractionSandbox, sendInteractionHostRequest, type InteractionSandboxSession } from '../api.ts'

const MESSAGE_SCHEMA = 'cartridgeflow.interaction_component_message.v1'

function hasScope(message: any, session: InteractionSandboxSession) {
  return message?.schema === MESSAGE_SCHEMA
    && message.channel_id === session.channel_id
    && message.run_id === session.run_id
    && message.cartridge_id === session.cartridge_id
    && message.node_id === session.node_id
    && message.component_id === session.component_id
    && message.interaction_id === session.interaction_id
}

export function InteractionSandboxFrame({
  pending,
  onDraft,
  onPropose,
}: {
  pending: any
  onDraft: (value: Record<string, any>, draftHash: string) => void
  onPropose: (actionId: string) => void
}) {
  const frameRef = useRef<HTMLIFrameElement | null>(null)
  const portRef = useRef<MessagePort | null>(null)
  const initializedRef = useRef(false)
  const readyRef = useRef(false)
  const [session, setSession] = useState<InteractionSandboxSession | null>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let active = true
    initializedRef.current = false
    readyRef.current = false
    setReady(false)
    setError('')
    const runId = String(pending?.run_id || '')
    const interactionId = String(pending?.interaction_id || '')
    fetchInteractionSandbox(runId, interactionId)
      .then((result) => { if (active) setSession(result) })
      .catch((reason) => { if (active) setError(reason?.message || '无法启动隔离交互界面') })
    return () => {
      active = false
      portRef.current?.close()
      portRef.current = null
      initializedRef.current = false
      if (runId && interactionId) void revokeInteractionSandbox(runId, interactionId).catch(() => undefined)
    }
  }, [pending?.interaction_id, pending?.run_id])

  useEffect(() => {
    if (!session || ready || error) return
    const timer = window.setTimeout(() => setError('隔离组件没有在 5 秒内完成安全握手'), 5000)
    return () => window.clearTimeout(timer)
  }, [error, ready, session])

  async function receive(message: any, activeSession: InteractionSandboxSession, port: MessagePort) {
    if (!hasScope(message, activeSession)) return
    if (message.type === 'channel.ready') {
      if (message?.payload?.nonce !== activeSession.nonce) {
        setError('隔离组件握手 nonce 无效')
        port.close()
        return
      }
      setReady(true)
      readyRef.current = true
      return
    }
    if (!readyRef.current && message.type !== 'channel.ready') return
    if (!activeSession.host_capabilities.includes(message.type)) {
      port.postMessage({ ...message, schema: 'cartridgeflow.interaction_host_message.v1', type: `${message.type}.error`, ok: false, error: 'capability_not_granted' })
      return
    }
    try {
      const response = await sendInteractionHostRequest(activeSession.run_id, activeSession.interaction_id, { ...message, nonce: activeSession.nonce })
      port.postMessage(response)
      if (message.type === 'draft.write') onDraft(message.payload?.value || {}, response?.payload?.draft_hash || '')
      if (message.type === 'interaction.propose' && response?.payload?.accepted) onPropose(String(response.payload.action_id || ''))
    } catch (reason: any) {
      port.postMessage({
        schema: 'cartridgeflow.interaction_host_message.v1',
        type: `${message.type}.error`,
        request_id: message.request_id,
        channel_id: activeSession.channel_id,
        run_id: activeSession.run_id,
        cartridge_id: activeSession.cartridge_id,
        node_id: activeSession.node_id,
        component_id: activeSession.component_id,
        interaction_id: activeSession.interaction_id,
        ok: false,
        error: reason?.message || 'host_request_failed',
      })
    }
  }

  function initialize() {
    const frameWindow = frameRef.current?.contentWindow
    if (!session || !frameWindow) return
    if (initializedRef.current) {
      portRef.current?.close()
      setReady(false)
      readyRef.current = false
      setError('隔离组件发生了未授权的重新加载，通道已撤销')
      return
    }
    initializedRef.current = true
    const channel = new MessageChannel()
    portRef.current = channel.port1
    channel.port1.onmessage = (event) => void receive(event.data, session, channel.port1)
    channel.port1.start()
    frameWindow.postMessage({
      schema: 'cartridgeflow.interaction_host_init.v1',
      type: 'host.init',
      channel_id: session.channel_id,
      nonce: session.nonce,
      run_id: session.run_id,
      cartridge_id: session.cartridge_id,
      node_id: session.node_id,
      component_id: session.component_id,
      interaction_id: session.interaction_id,
      input_revision: session.input_revision,
      input: session.input,
      host_capabilities: session.host_capabilities,
    }, '*', [channel.port2])
  }

  if (error) return <div className="cf-sandbox-status error"><strong>隔离组件已阻断</strong><span>{error}</span></div>
  if (!session) return <div className="cf-sandbox-status"><strong>正在启动隔离组件</strong><span>准备独立资源进程与一次性通道…</span></div>
  return (
    <div className="cf-interaction-sandbox">
      <div className="cf-sandbox-security"><span className={ready ? 'ready' : ''}>{ready ? '安全通道已连接' : '等待安全握手'}</span><code>网络拒绝 · 独立资源进程 · {session.policy?.memory_mb ? `${session.policy.memory_mb} MB` : '浏览器站点隔离'}</code></div>
      <iframe
        ref={(node) => {
          frameRef.current = node
          if (node) node.setAttribute('credentialless', '')
        }}
        title={`${session.component_id} sandboxed interaction`}
        src={session.url}
        sandbox="allow-scripts"
        allow=""
        referrerPolicy="no-referrer"
        onLoad={initialize}
      />
    </div>
  )
}
