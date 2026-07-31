import fs from 'node:fs/promises'

const [, , debuggerPort = '9333', url, outputPath, width = '1536', height = '864', actionExpression = '', metricsOutputPath = ''] = process.argv

if (!url || !outputPath) {
  throw new Error('Usage: node capture_workbench.mjs <debug-port> <url> <output.png> <width> <height>')
}

const target = await fetch(`http://127.0.0.1:${debuggerPort}/json/new?${encodeURIComponent(url)}`, { method: 'PUT' }).then((response) => response.json())
const socket = new WebSocket(target.webSocketDebuggerUrl)
const pending = new Map()
const runtimeDiagnostics = []
let commandId = 0

await new Promise((resolve, reject) => {
  socket.addEventListener('open', resolve, { once: true })
  socket.addEventListener('error', reject, { once: true })
})

socket.addEventListener('message', (event) => {
  const message = JSON.parse(String(event.data))
  if (message.method === 'Runtime.exceptionThrown') {
    runtimeDiagnostics.push(message.params?.exceptionDetails?.exception?.description || message.params?.exceptionDetails?.text || 'Runtime exception')
  }
  if (message.method === 'Runtime.consoleAPICalled' && ['error', 'warning'].includes(message.params?.type)) {
    runtimeDiagnostics.push((message.params?.args || []).map((item) => item.value || item.description || '').join(' '))
  }
  if (!message.id || !pending.has(message.id)) return
  const { resolve, reject } = pending.get(message.id)
  pending.delete(message.id)
  if (message.error) reject(new Error(message.error.message))
  else resolve(message.result)
})

function command(method, params = {}) {
  const id = ++commandId
  socket.send(JSON.stringify({ id, method, params }))
  return new Promise((resolve, reject) => pending.set(id, { resolve, reject }))
}

await command('Page.enable')
await command('Runtime.enable')
await command('Emulation.setDeviceMetricsOverride', {
  width: Number(width),
  height: Number(height),
  deviceScaleFactor: 1,
  mobile: false,
})
await command('Page.navigate', { url })

const deadline = Date.now() + 20000
let ready = false
while (Date.now() < deadline) {
  const result = await command('Runtime.evaluate', {
    expression: `Boolean(document.querySelector('.cf-workbench-header') && document.querySelector('.flow-node-card, .react-flow__node'))`,
    returnByValue: true,
  })
  if (result.result?.value) {
    ready = true
    break
  }
  await new Promise((resolve) => setTimeout(resolve, 250))
}

if (!ready) {
  const failure = await command('Runtime.evaluate', {
    expression: `JSON.stringify({ body: document.body?.innerText?.slice(0, 1200) || '', root: document.querySelector('#root')?.innerHTML?.slice(0, 800) || '', vite: document.querySelector('vite-error-overlay')?.shadowRoot?.textContent?.slice(0, 2400) || '' })`,
    returnByValue: true,
  })
  throw new Error(`Workbench did not finish rendering within 20 seconds: ${failure.result?.value || '{}'}; runtime=${JSON.stringify(runtimeDiagnostics.slice(-12))}`)
}
if (actionExpression) {
  const actionResult = await command('Runtime.evaluate', { expression: actionExpression, awaitPromise: true })
  if (actionResult.exceptionDetails) {
    const description = actionResult.exceptionDetails.exception?.description
      || actionResult.exceptionDetails.text
      || 'Unknown browser evaluation error'
    throw new Error(`Action expression failed: ${description}`)
  }
  await new Promise((resolve) => setTimeout(resolve, 400))
}
const interactionSequence = await command('Runtime.evaluate', {
  expression: `window.__cfInteractionSequence ? JSON.stringify(window.__cfInteractionSequence) : ''`,
  returnByValue: true,
})
if (interactionSequence.result?.value) {
  const sequence = JSON.parse(interactionSequence.result.value)
  for (const step of sequence) {
    let point = null
    for (let attempt = 0; attempt < 20; attempt++) {
      const target = await command('Runtime.evaluate', {
        expression: `(() => { const element = document.querySelector(${JSON.stringify(step.selector)}); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } })()`,
        returnByValue: true,
      })
      point = target.result?.value || null
      if (point) break
      await new Promise((resolve) => setTimeout(resolve, 100))
    }
    if (!point) throw new Error(`Interaction target not found: ${step.selector}`)
    const right = step.type === 'contextmenu'
    const button = right ? 'right' : 'left'
    const buttons = right ? 2 : 1
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button, buttons, clickCount: 1 })
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button, buttons: 0, clickCount: 1 })
    await new Promise((resolve) => setTimeout(resolve, Number(step.wait || 450)))
  }
}
const detailCards = await command('Runtime.evaluate', {
  expression: `window.__cfOpenDetailCards
    ? JSON.stringify(window.__cfOpenDetailCards)
    : window.__cfOpenEditorNodeIds
      ? JSON.stringify(window.__cfOpenEditorNodeIds.map((nodeId) => ({ nodeId, section: 'contract' })))
      : ''`,
  returnByValue: true,
})
if (detailCards.result?.value) {
  for (const detailCard of JSON.parse(detailCards.result.value)) {
    const nodeId = detailCard.nodeId
    const section = detailCard.section || 'contract'
    const target = await command('Runtime.evaluate', {
      expression: `(() => { const element = document.querySelector('.react-flow__node[data-id="' + ${JSON.stringify(nodeId)} + '"]'); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } })()`,
      returnByValue: true,
    })
    if (!target.result?.value) throw new Error(`Node target not found: ${nodeId}`)
    const point = target.result.value
    await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'right', buttons: 2, clickCount: 1 })
    await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'right', buttons: 0, clickCount: 1 })
    await new Promise((resolve) => setTimeout(resolve, 700))
    if (detailCard.menuOnly) {
      const menuTarget = await command('Runtime.evaluate', {
        expression: `(() => { const element = document.querySelector('.cf-graph-context-menu .cf-graph-submenu-item > button'); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } })()`,
        returnByValue: true,
      })
      if (!menuTarget.result?.value) throw new Error(`Node detail menu not found: ${nodeId}`)
      await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: menuTarget.result.value.x, y: menuTarget.result.value.y, button: 'none', buttons: 0 })
      await new Promise((resolve) => setTimeout(resolve, 500))
      continue
    }
    const opened = await command('Runtime.evaluate', {
      expression: `(() => { const button = document.querySelector('.cf-node-detail-submenu button[data-section="${section}"]'); if (!button) return false; button.click(); return true })()`,
      returnByValue: true,
    })
    if (!opened.result?.value) throw new Error(`Node detail command not found: ${nodeId}:${section}`)
    await new Promise((resolve) => setTimeout(resolve, 1300))
  }
  await command('Runtime.evaluate', {
    expression: `window.__cfViewportTransformAfterEditorOpen = document.querySelector('.react-flow__viewport')?.style.transform || ''`,
  })
}
const clickSelector = await command('Runtime.evaluate', {
  expression: `window.__cfClickSelector || ''`,
  returnByValue: true,
})
if (clickSelector.result?.value) {
  const target = await command('Runtime.evaluate', {
    expression: `(() => { const element = document.querySelector(${JSON.stringify(clickSelector.result.value)}); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } })()`,
    returnByValue: true,
  })
  if (!target.result?.value) throw new Error(`Click selector not found: ${clickSelector.result.value}`)
  const point = target.result.value
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'left', buttons: 1, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'left', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 350))
}
const hoverSelector = await command('Runtime.evaluate', {
  expression: `window.__cfHoverSelector || ''`,
  returnByValue: true,
})
if (hoverSelector.result?.value) {
  const target = await command('Runtime.evaluate', {
    expression: `(() => { const element = document.querySelector(${JSON.stringify(hoverSelector.result.value)}); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + Math.min(rect.height / 2, 42)) } })()`,
    returnByValue: true,
  })
  if (!target.result?.value) throw new Error(`Hover selector not found: ${hoverSelector.result.value}`)
  await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: target.result.value.x, y: target.result.value.y, button: 'none', buttons: 0 })
  await new Promise((resolve) => setTimeout(resolve, 350))
}
const dragSelector = await command('Runtime.evaluate', {
  expression: `window.__cfDragSelector || ''`,
  returnByValue: true,
})
if (dragSelector.result?.value) {
  const dragDelta = await command('Runtime.evaluate', {
    expression: `window.__cfDragDelta ? JSON.stringify(window.__cfDragDelta) : ''`,
    returnByValue: true,
  })
  const delta = dragDelta.result?.value ? JSON.parse(dragDelta.result.value) : { x: 120, y: 60 }
  const target = await command('Runtime.evaluate', {
    expression: `(() => { const element = document.querySelector(${JSON.stringify(dragSelector.result.value)}); if (!element) return null; const rect = element.getBoundingClientRect(); const editor = element.closest('.cf-node-editor-viewport')?.getBoundingClientRect(); window.__cfEditorRectBeforeDrag = editor ? { left: editor.left, top: editor.top, width: editor.width, height: editor.height } : null; window.__cfViewportTransformBeforeAction = document.querySelector('.react-flow__viewport')?.style.transform || ''; return { x: Math.round(rect.left + rect.width * .36), y: Math.round(rect.top + rect.height / 2) } })()`,
    returnByValue: true,
  })
  if (!target.result?.value) throw new Error(`Drag selector not found: ${dragSelector.result.value}`)
  const from = target.result.value
  const to = { x: from.x + Number(delta.x || 0), y: from.y + Number(delta.y || 0) }
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: from.x, y: from.y, button: 'left', buttons: 1, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: from.x + (to.x - from.x) / 2, y: from.y + (to.y - from.y) / 2, button: 'left', buttons: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: to.x, y: to.y, button: 'left', buttons: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: to.x, y: to.y, button: 'left', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 500))
}
const clickTest = await command('Runtime.evaluate', {
  expression: `window.__cfClickTest ? JSON.stringify(window.__cfClickTest) : ''`,
  returnByValue: true,
})
if (clickTest.result?.value) {
  const click = JSON.parse(clickTest.result.value)
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: click.x, y: click.y, button: 'left', buttons: 1, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: click.x, y: click.y, button: 'left', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 250))
}
const rightClickSelector = await command('Runtime.evaluate', {
  expression: `window.__cfRightClickSelector || ''`,
  returnByValue: true,
})
if (rightClickSelector.result?.value) {
  const target = await command('Runtime.evaluate', {
    expression: `(() => { const element = document.querySelector(${JSON.stringify(rightClickSelector.result.value)}); if (!element) return null; const rect = element.getBoundingClientRect(); return { x: Math.round(rect.left + rect.width / 2), y: Math.round(rect.top + rect.height / 2) } })()`,
    returnByValue: true,
  })
  if (!target.result?.value) throw new Error(`Right-click selector not found: ${rightClickSelector.result.value}`)
  const point = target.result.value
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: point.x, y: point.y, button: 'right', buttons: 2, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: point.x, y: point.y, button: 'right', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 700))
}
const rightClickTest = await command('Runtime.evaluate', {
  expression: `window.__cfRightClickTest ? JSON.stringify(window.__cfRightClickTest) : ''`,
  returnByValue: true,
})
if (rightClickTest.result?.value) {
  const click = JSON.parse(rightClickTest.result.value)
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: click.x, y: click.y, button: 'right', buttons: 2, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: click.x, y: click.y, button: 'right', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 450))
}
const afterRightClick = await command('Runtime.evaluate', {
  expression: `window.__cfAfterRightClickExpression || ''`,
  returnByValue: true,
})
if (afterRightClick.result?.value) {
  await command('Runtime.evaluate', { expression: afterRightClick.result.value, awaitPromise: true })
  await new Promise((resolve) => setTimeout(resolve, 1100))
}
const doubleClickTest = await command('Runtime.evaluate', {
  expression: `window.__cfDoubleClickTest ? JSON.stringify(window.__cfDoubleClickTest) : ''`,
  returnByValue: true,
})
if (doubleClickTest.result?.value) {
  const click = JSON.parse(doubleClickTest.result.value)
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: click.x, y: click.y, button: 'left', buttons: 1, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: click.x, y: click.y, button: 'left', buttons: 0, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: click.x, y: click.y, button: 'left', buttons: 1, clickCount: 2 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: click.x, y: click.y, button: 'left', buttons: 0, clickCount: 2 })
  await new Promise((resolve) => setTimeout(resolve, 450))
}
const panTest = await command('Runtime.evaluate', {
  expression: `window.__cfPanTest ? JSON.stringify(window.__cfPanTest) : ''`,
  returnByValue: true,
})
if (panTest.result?.value) {
  const pan = JSON.parse(panTest.result.value)
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: pan.fromX, y: pan.fromY, button: 'right', buttons: 2, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: pan.toX, y: pan.toY, button: 'right', buttons: 2 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: pan.toX, y: pan.toY, button: 'right', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 350))
}
const selectionTest = await command('Runtime.evaluate', {
  expression: `window.__cfSelectionTest ? JSON.stringify(window.__cfSelectionTest) : ''`,
  returnByValue: true,
})
if (selectionTest.result?.value) {
  const selection = JSON.parse(selectionTest.result.value)
  await command('Input.dispatchMouseEvent', { type: 'mousePressed', x: selection.fromX, y: selection.fromY, button: 'left', buttons: 1, clickCount: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseMoved', x: selection.toX, y: selection.toY, button: 'left', buttons: 1 })
  await command('Input.dispatchMouseEvent', { type: 'mouseReleased', x: selection.toX, y: selection.toY, button: 'left', buttons: 0, clickCount: 1 })
  await new Promise((resolve) => setTimeout(resolve, 350))
}
await new Promise((resolve) => setTimeout(resolve, 700))

const metrics = await command('Runtime.evaluate', {
  expression: `JSON.stringify({
    viewport: { width: window.innerWidth, height: window.innerHeight },
    locationPath: window.location.pathname,
    page: { clientWidth: document.documentElement.clientWidth, scrollWidth: document.documentElement.scrollWidth, clientHeight: document.documentElement.clientHeight, scrollHeight: document.documentElement.scrollHeight },
    canvas: (() => { const element = document.querySelector('.cf-flow-graph-shell'); return element ? { clientWidth: element.clientWidth, scrollWidth: element.scrollWidth, clientHeight: element.clientHeight, scrollHeight: element.scrollHeight } : null })(),
    selectedNode: (() => { const element = document.querySelector('.react-flow__node.selected, .react-flow__node:has(.flow-node-card.selected)'); if (!element) return null; const rect = element.getBoundingClientRect(); return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height } })(),
    nodeDrawer: (() => { const element = document.querySelector('.cf-node-drawer'); if (!element) return null; const rect = element.getBoundingClientRect(); return { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height } })(),
    nodeEditors: [...document.querySelectorAll('.cf-node-editor-viewport')].map((element) => { const rect = element.getBoundingClientRect(); return { editorId: element.dataset.editorId || '', nodeId: element.dataset.nodeId || '', section: element.dataset.section || '', className: element.className, left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height } }),
    editorRectBeforeDrag: window.__cfEditorRectBeforeDrag || null,
    detailConnectorCounts: [...document.querySelectorAll('.cf-node-detail-connectors')].map((element) => Number(element.getAttribute('data-connector-count') || 0)),
    graphNodes: [...document.querySelectorAll('.react-flow__node[data-id]')].map((element) => element.getAttribute('data-id') || ''),
    nodePresentations: [...document.querySelectorAll('.flow-node-card[data-node-id]')].map((element) => ({
      nodeId: element.dataset.nodeId || '',
      kind: element.dataset.nodeKind || '',
      health: element.dataset.configHealth || '',
      sectionTitles: [...element.querySelectorAll('.flow-node-detail-band h4')].map((item) => item.textContent?.trim() || ''),
      factLabels: [...element.querySelectorAll('.flow-node-detail-band dt, .flow-node-io-row > span')].map((item) => item.textContent?.trim() || ''),
      status: element.querySelector('.flow-node-status')?.textContent?.trim() || '',
    })),
    detailPresentations: [...document.querySelectorAll('.cf-node-satellite')].map((element) => ({
      nodeId: element.dataset.nodeId || '',
      kind: element.dataset.nodeKind || '',
      section: element.dataset.detailSection || '',
      title: element.querySelector('.cf-node-detail-card > header strong')?.textContent?.trim() || '',
      factLabels: [...element.querySelectorAll('.cf-node-detail-card dt')].map((item) => item.textContent?.trim() || ''),
    })),
    pinnedNodeEditors: document.querySelectorAll('.cf-node-drawer-pin.active').length,
    pinnedDetailStorage: Object.fromEntries(Object.keys(localStorage).filter((key) => key.startsWith('cartridgeflow.pinned-node-details.v1:')).map((key) => [key, localStorage.getItem(key)])),
    viewportTransform: document.querySelector('.react-flow__viewport')?.style.transform || '',
    viewportTransformBeforeAction: window.__cfViewportTransformBeforeAction || '',
    viewportTransformAfterEditorOpen: window.__cfViewportTransformAfterEditorOpen || '',
    debug: window.__cfDebug || null,
    selectedFlowNodes: document.querySelectorAll('.react-flow__node.selected').length,
    runStateNodes: {
      idle: document.querySelectorAll('.flow-node-card.node-run-idle').length,
      running: document.querySelectorAll('.flow-node-card.node-run-running').length,
      completed: document.querySelectorAll('.flow-node-card.node-run-completed').length,
      paused: document.querySelectorAll('.flow-node-card.node-run-paused').length,
      failed: document.querySelectorAll('.flow-node-card.node-run-failed').length,
    },
    historyLogButtons: document.querySelectorAll('.cf-canvas-history-log').length,
    contextMenus: document.querySelectorAll('.cf-graph-context-menu').length,
    contextMenuHtml: document.querySelector('.cf-graph-context-menu')?.innerHTML.slice(0, 1200) || '',
    runLogDialog: Boolean(document.querySelector('.cf-run-log-dialog')),
    runLogActionLabels: [...document.querySelectorAll('.cf-run-log-actions button')].map((element) => element.textContent?.trim() || ''),
    backgrounds: [...document.querySelectorAll('.react-flow__background')].map((element) => ({
      display: getComputedStyle(element).display,
      opacity: getComputedStyle(element).opacity,
      zIndex: getComputedStyle(element).zIndex,
      html: element.outerHTML.slice(0, 500)
    }))
  })`,
  returnByValue: true,
})
const screenshot = await command('Page.captureScreenshot', { format: 'png', fromSurface: true, captureBeyondViewport: false })
await fs.mkdir(new URL('.', `file:///${outputPath.replaceAll('\\', '/')}`).pathname, { recursive: true }).catch(() => {})
await fs.writeFile(outputPath, Buffer.from(screenshot.data, 'base64'))
if (metricsOutputPath) {
  await fs.mkdir(new URL('.', `file:///${metricsOutputPath.replaceAll('\\', '/')}`).pathname, { recursive: true }).catch(() => {})
  await fs.writeFile(metricsOutputPath, metrics.result?.value || '{}', 'utf8')
}
console.log(metrics.result?.value || '{}')
socket.close()
