import type { ReactNode } from 'react'
import { ChevronRight, Sparkles } from 'lucide-react'
import type { CreatorRunnerDelivery } from '../api/client.ts'
import type { CreatorClarification, CreatorPackage, CreatorPossibility, CreatorProjection } from '../api/types.ts'
import { COMPOSE_INPUT_ID, MIN_GOAL_LENGTH } from '../config.ts'
import { copy } from '../copy.ts'
import { Button, Card, ComposeBar, EmptyHint, GoalChip } from '../ui/index.ts'
import { nodeReviewState, type StageId } from './model.ts'

export type StageContext = {
  creator: CreatorProjection | null
  goal: string
  stage: StageId
  busy: boolean
  error: string
  input: string
  clarification: CreatorClarification | null
  possibilities: CreatorPossibility[]
  packageResult: CreatorPackage | null
  packageError: string
  runnerDelivery: CreatorRunnerDelivery | null
  onInput: (value: string) => void
  onSubmit: () => void
  onClarify: (value: string) => void
  onChoose: (intent: string) => void
  onSkip: () => void
  onRetry: () => void
  onOpenGap?: (nodeId: string) => void
}

function EmptyCanvas({ stage }: { stage: StageId }) {
  return <EmptyHint
    icon={<Sparkles />}
    title={copy.emptyTitle}
    detail={stage === 'connect-ai' ? copy.emptyBeforeConnect : copy.emptyBeforeDescribe}
  />
}

function DescribeStage({ input, onInput, onSubmit }: StageContext) {
  return <>
    <ComposeBar
      id={COMPOSE_INPUT_ID}
      value={input}
      placeholder={copy.composePlaceholder}
      submitLabel={<>{copy.composeSubmit} <ChevronRight /></>}
      minLength={MIN_GOAL_LENGTH}
      onChange={onInput}
      onSubmit={onSubmit}
    />
    <p className="compose-hint">{copy.composeHint}</p>
  </>
}

function GeneratingStage() {
  return <Card kicker={copy.generatingKicker} title={copy.generatingTitle} role="status">
    <p>{copy.generatingBody}</p>
  </Card>
}

function FailStage({ error, goal, onRetry }: StageContext) {
  return <Card kicker={copy.failKicker} title={copy.failTitle} role="alert">
    <p>{error}</p>
    <GoalChip label={copy.goalKept} value={goal} />
    <Button onClick={onRetry}>{copy.retry}</Button>
  </Card>
}

function ClarifyStage({ goal, clarification, input, onInput, onSubmit, onClarify }: StageContext) {
  if (!clarification) return null
  return <Card kicker={copy.clarifyKicker} title={clarification.question}>
    <GoalChip label={copy.goal} value={goal} />
    <p>{clarification.why_it_matters}</p>
    <div className="answers">{clarification.suggested_answers.map((answer) => <Button variant="ghost" key={answer} onClick={() => onClarify(answer)}>{answer}</Button>)}</div>
    <ComposeBar value={input} placeholder={copy.clarifyPlaceholder} submitLabel={copy.clarifySubmit} minLength={2} onChange={onInput} onSubmit={onSubmit} />
  </Card>
}

function DirectionsStage({ goal, possibilities, onChoose, onSkip }: StageContext) {
  return <>
    <GoalChip label={copy.goal} value={goal} />
    <div className="directions">
      {possibilities.map((item) => <article className="direction" key={item.id}>
        <h3>{item.title}</h3>
        <div className="body-copy">
          <div><dt>{copy.outcome}</dt><dd>{item.outcome}</dd></div>
          <div><dt>{copy.whyItFits}</dt><dd>{item.why_it_fits}</dd></div>
        </div>
        <Button variant="soft" onClick={() => onChoose(item.recipe.intent)}>{copy.chooseDirection}</Button>
      </article>)}
    </div>
    <Button variant="skip" onClick={onSkip}>{copy.skipDirections}</Button>
  </>
}

function PackageStage({ creator, packageResult, packageError, runnerDelivery, busy, onOpenGap }: StageContext) {
  if (!creator) return null
  const blockers = creator.trusted_recipe.nodes.filter((node) => nodeReviewState(creator, node) === 'unresolved')
  const heading = packageError
    ? copy.package.fail
    : blockers.length
      ? copy.package.notReady
      : runnerDelivery?.status === 'trust_required'
        ? copy.package.trust
        : runnerDelivery
          ? copy.package.installed
          : packageResult
            ? copy.package.signed
            : busy
              ? copy.package.packing
              : copy.package.notReady
  const body = packageError || blockers.length || busy
    ? null
    : runnerDelivery?.status === 'trust_required'
      ? copy.package.trustBody
      : runnerDelivery
        ? copy.package.installedBody
        : packageResult
          ? copy.package.signedBody
          : copy.package.notReadyBody
  return <div className="pack-inner" role={packageError ? 'alert' : undefined}>
    <div className="pack-scroll">
      <strong>{packageError || heading}</strong>
      {blockers.length ? <ul>{blockers.map((node, index) => <li key={node.id}><em>{String(index + 1).padStart(2, '0')}</em><button type="button" className="runtime-text-link" onClick={() => onOpenGap?.(node.id)}>{node.label}</button></li>)}</ul> : body ? <p className="pack-body">{body}</p> : null}
    </div>
  </div>
}

const beforeRecipe: Partial<Record<StageId, (ctx: StageContext) => ReactNode>> = {
  describe: (ctx) => <DescribeStage {...ctx} />,
  clarify: (ctx) => <ClarifyStage {...ctx} />,
  choose: (ctx) => <DirectionsStage {...ctx} />,
}

export function StageLayer(ctx: StageContext) {
  if (ctx.creator) {
    return <div className="stage-layer is-docked"><div className="pack-corner"><PackageStage {...ctx} /></div></div>
  }

  const overlay = ctx.busy
    ? <GeneratingStage />
    : ctx.error
      ? <FailStage {...ctx} />
      : beforeRecipe[ctx.stage]?.(ctx)

  return <div className="stage-layer">
    <EmptyCanvas stage={ctx.stage} />
    {overlay}
  </div>
}
