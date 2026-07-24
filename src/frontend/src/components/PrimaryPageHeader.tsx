import type { ReactNode } from 'react'

type PrimaryPageHeaderProps = {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
  className?: string
  actionsClassName?: string
}

export default function PrimaryPageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = '',
  actionsClassName = '',
}: PrimaryPageHeaderProps) {
  const headerClassName = ['cf-primary-page-header', className].filter(Boolean).join(' ')
  const actionClassName = ['cf-primary-page-header-actions', actionsClassName].filter(Boolean).join(' ')

  return (
    <header className={headerClassName}>
      <div className="cf-primary-page-header-copy">
        <span className="cf-primary-page-kicker">{eyebrow}</span>
        <h1 className="cf-primary-page-title">{title}</h1>
        <p className="cf-primary-page-description">{description}</p>
      </div>
      {actions ? <div className={actionClassName}>{actions}</div> : null}
    </header>
  )
}
