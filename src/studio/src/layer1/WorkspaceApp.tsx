import { useEffect, useState, type FormEvent } from 'react'
import { copy } from '../copy.ts'
import { Alert, Button, Dialog, Field, TextInput } from '../ui/index.ts'
import { ConnectDialog } from './ConnectDialog.tsx'
import { Canvas } from './Canvas.tsx'
import { NodeDetail } from './NodeDetail.tsx'
import { Layer2Overlay } from '../layer2/Overlay.tsx'
import { ResourcePool } from './ResourcePool.tsx'
import { NarrowTabs, NextBar, ProjectMenu, Shell, WorkspaceHeader } from './Shell.tsx'
import { StageLayer } from './stages.tsx'
import { Steward } from './Steward.tsx'
import { RunBlocker, RuntimeDesk, RuntimeToasts } from './RuntimeDesk.tsx'
import { useWorkspace } from './useWorkspace.ts'
import type { ReviewState } from './model.ts'

export function WorkspaceApp({ projectId }: { projectId: string }) {
  const workspace = useWorkspace(projectId)
  const [runtimeOpen, setRuntimeOpen] = useState(false)
  const [reviewFilter, setReviewFilter] = useState<ReviewState | ''>('')
  const [projectAction, setProjectAction] = useState<{ kind: 'rename' | 'delete'; name: string } | null>(null)
  const showSteward = Boolean(workspace.creator && (workspace.stewardOpen || (workspace.narrow && workspace.tab === 'steward')))

  useEffect(() => {
    if (new URLSearchParams(window.location.search).get('runtime') === '1') setRuntimeOpen(true)
  }, [])

  return <>
    <Shell
      narrow={workspace.narrow}
      header={<WorkspaceHeader
        projectName={workspace.projectName}
        section={runtimeOpen ? copy.runtimeDesk : workspace.layer2Node ? copy.layer2Kicker : undefined}
        projectMenu={workspace.projectMenuOpen ? <ProjectMenu
          projectId={projectId}
          projects={workspace.projects}
          onNew={workspace.startNewProject}
          onRename={(name) => setProjectAction({ kind: 'rename', name })}
          onDelete={(name) => setProjectAction({ kind: 'delete', name })}
        /> : null}
        syncLabel={workspace.syncLabel}
        connected={workspace.connected}
        connectionLabel={workspace.connectionLabel}
        onConnect={() => workspace.setConnectOpen(true)}
        onOpenSettings={() => workspace.setSettingsOpen(true)}
        onToggleSteward={workspace.creator ? () => {
          if (workspace.narrow) workspace.setTab('steward')
          else workspace.setStewardOpen((open) => !open)
        } : undefined}
        stewardOn={workspace.stewardOpen}
        onToggleProjectMenu={() => workspace.setProjectMenuOpen((open) => !open)}
      />}
      next={<NextBar
        guidance={workspace.guidance}
        stats={workspace.stats}
        narrow={workspace.narrow}
        onAction={() => {
          if (workspace.guidance.action === 'download' || workspace.guidance.action === 'runner') {
            workspace.closeLayer2()
            setRuntimeOpen(true)
            return
          }
          if (workspace.guidance.action === 'open-node' && workspace.guidance.nodeId) {
            const node = workspace.creator?.trusted_recipe.nodes.find((item) => item.id === workspace.guidance.nodeId)
            if (node?.resolution?.status === 'unresolved') {
              workspace.openLayer2(workspace.guidance.nodeId)
              return
            }
          }
          workspace.runPrimaryAction()
        }}
        reviewFilter={reviewFilter}
        onFilterReview={setReviewFilter}
      />}
      tabs={<NarrowTabs tab={workspace.tab} onTab={workspace.setTab} />}
    >
      <div className={`body${showSteward && !workspace.narrow ? ' has-steward' : ''}${workspace.showDetail && !workspace.narrow ? ' has-detail' : ''}`}>
        {showSteward && (!workspace.narrow || workspace.tab === 'steward') ? <Steward
          messages={workspace.messages}
          input={workspace.input}
          busy={workspace.busy}
          error={workspace.error}
          scope={workspace.stewardScope}
          contextNodes={workspace.contextNodes}
          preview={workspace.recipePreview}
          onInput={workspace.setInput}
          onSubmit={workspace.submitComposer}
          onScope={workspace.setStewardScope}
          onApplyPreview={() => void workspace.applyRecipePreview()}
          onRejectPreview={workspace.rejectRecipePreview}
          onClearContext={workspace.clearContext}
          onRemoveContext={workspace.removeContext}
          onClose={workspace.narrow ? undefined : () => workspace.setStewardOpen(false)}
        /> : null}
        <section className={`canvas-region${workspace.narrow && workspace.tab !== 'canvas' ? ' is-hidden' : ''}`} aria-label="语义画布">
          <div className="canvas-surface">
            <Canvas
              creator={workspace.creator}
              selectedId={workspace.selectedId}
              contextIds={workspace.contextIds}
              preview={workspace.recipePreview}
              vertical={workspace.narrow}
              onSelect={workspace.selectCanvasNode}
              onOpenLayer={workspace.openLayer2}
              onApplyPreview={() => void workspace.applyRecipePreview()}
              onRejectPreview={workspace.rejectRecipePreview}
              reviewFilter={reviewFilter}
            />
            <StageLayer
              creator={workspace.creator}
              goal={workspace.goal}
              stage={workspace.guidance.stage}
              busy={workspace.busy}
              error={workspace.error}
              input={workspace.input}
              clarification={workspace.clarification}
              possibilities={workspace.possibilities}
              packageResult={workspace.packageResult}
              packageError={workspace.packageError}
              runnerDelivery={workspace.runnerDelivery}
              onInput={workspace.setInput}
              onSubmit={workspace.submitComposer}
              onClarify={workspace.clarify}
              onChoose={workspace.chooseDirection}
              onSkip={workspace.skipDirections}
              onRetry={workspace.retryDiscover}
              onOpenGap={(nodeId) => workspace.openLayer2(nodeId)}
            />
            {workspace.loading ? <div className="loading">{copy.loadingProject}</div> : null}
          </div>
        </section>
        {workspace.showDetail && workspace.creator && workspace.selectedNode && (!workspace.narrow || workspace.tab === 'detail') ? <section className={`detail-region${workspace.narrow && workspace.tab !== 'detail' ? ' is-hidden' : ''}`}>
          <NodeDetail
            creator={workspace.creator}
            node={workspace.selectedNode}
            busy={workspace.busy}
            returned={workspace.returnedFromWorkshop}
            onCreatorChange={workspace.saveCreator}
            onClose={workspace.closeDetail}
            onOpenNode={workspace.openNode}
            onOpenLayer={workspace.openLayer2}
            onModelRequired={workspace.requireModel}
          />
        </section> : null}
      </div>
    </Shell>
    {workspace.connectOpen ? <ConnectDialog current={workspace.aiStatus} onConnect={workspace.connect} onClose={() => workspace.setConnectOpen(false)} /> : null}
    {workspace.settingsOpen ? <ResourcePool onClose={() => workspace.setSettingsOpen(false)} /> : null}
    {projectAction?.kind === 'rename' ? <RenameProjectDialog
      name={projectAction.name}
      onClose={() => setProjectAction(null)}
      onRename={workspace.renameProject}
    /> : null}
    {projectAction?.kind === 'delete' ? <DeleteProjectDialog
      name={projectAction.name}
      onClose={() => setProjectAction(null)}
      onDelete={workspace.deleteProject}
    /> : null}
    {workspace.layer2Node && workspace.creator ? <Layer2Overlay
      creator={workspace.creator}
      node={workspace.layer2Node}
      flowId={workspace.layer2Flows[workspace.layer2Node.id]}
      onClose={workspace.closeLayer2}
      onPublished={(nodeId) => void workspace.finishLayer2(nodeId, true)}
      onOpened={workspace.rememberLayer2}
      onCreator={workspace.saveCreator}
      onOpenResources={() => {
        workspace.closeLayer2()
        workspace.setSettingsOpen(true)
      }}
    /> : null}
    {runtimeOpen ? <RuntimeDesk
      creator={workspace.creator}
      packageResult={workspace.packageResult}
      onClose={() => setRuntimeOpen(false)}
      onPackage={() => workspace.buildPackage()}
      onOpenGap={(nodeId) => {
        setRuntimeOpen(false)
        workspace.openLayer2(nodeId)
      }}
      onToggleSteward={() => workspace.setStewardOpen(true)}
    /> : null}
    <RunBlocker />
    <RuntimeToasts />
  </>
}

function RenameProjectDialog({
  name,
  onClose,
  onRename,
}: {
  name: string
  onClose: () => void
  onRename: (name: string) => Promise<void>
}) {
  const [value, setValue] = useState(name)
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault()
    if (!value.trim() || working) return
    setWorking(true)
    setError('')
    try {
      await onRename(value.trim())
      onClose()
    } catch {
      setError(copy.projectActionFail)
      setWorking(false)
    }
  }
  return <Dialog title={copy.renameProjectTitle} locked={working} onClose={onClose}>
    <form onSubmit={submit}>
      <Field label={copy.projectName}><TextInput autoFocus maxLength={16} value={value} disabled={working} onChange={(event) => setValue(event.currentTarget.value)} /></Field>
      {error ? <Alert>{error}</Alert> : null}
      <div className="dialog-foot"><span /><Button variant="ghost" disabled={working} onClick={onClose}>{copy.cancel}</Button><Button type="submit" disabled={working || !value.trim()}>{copy.renameProject}</Button></div>
    </form>
  </Dialog>
}

function DeleteProjectDialog({
  name,
  onClose,
  onDelete,
}: {
  name: string
  onClose: () => void
  onDelete: () => Promise<void>
}) {
  const [working, setWorking] = useState(false)
  const [error, setError] = useState('')
  const remove = async () => {
    if (working) return
    setWorking(true)
    setError('')
    try {
      await onDelete()
    } catch {
      setError(copy.projectActionFail)
      setWorking(false)
    }
  }
  return <Dialog title={copy.deleteProjectTitle} description={`${name} · ${copy.deleteProjectHint}`} locked={working} onClose={onClose}>
    <form onSubmit={(event) => { event.preventDefault(); void remove() }}>
      {error ? <Alert>{error}</Alert> : null}
      <div className="dialog-foot"><span /><Button autoFocus variant="ghost" disabled={working} onClick={onClose}>{copy.cancel}</Button><Button type="submit" disabled={working}>{copy.confirmDeleteProject}</Button></div>
    </form>
  </Dialog>
}
