import { useEffect, type ButtonHTMLAttributes, type FormEvent, type InputHTMLAttributes, type ReactNode, type TextareaHTMLAttributes } from 'react'
import { X } from 'lucide-react'
import type { ReviewState } from '../layer1/model.ts'
import { statusCopy } from '../layer1/model.ts'
import { copy } from '../copy.ts'

export function cx(...parts: Array<string | false | null | undefined>) {
  return parts.filter(Boolean).join(' ')
}

type ButtonVariant = 'primary' | 'ghost' | 'soft' | 'icon' | 'skip'

export function Button({
  variant = 'primary',
  className,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant }) {
  const tone = variant === 'primary' ? 'btn' : variant === 'ghost' ? 'btn btn-ghost' : variant === 'soft' ? 'btn btn-soft' : variant === 'icon' ? 'icon-btn' : 'skip'
  return <button type={props.type || 'button'} className={cx(tone, className)} {...props} />
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string
  hint?: ReactNode
  children: ReactNode
}) {
  return <label>{label}{hint}{children}</label>
}

export function TextInput(props: InputHTMLAttributes<HTMLInputElement>) {
  return <input {...props} />
}

export function TextArea(props: TextareaHTMLAttributes<HTMLTextAreaElement>) {
  return <textarea {...props} />
}

export function SegmentedControl<T extends string>({
  label,
  value,
  options,
  disabled,
  onChange,
}: {
  label: string
  value: T
  options: Array<{ id: T; label: string; badge?: string }>
  disabled?: boolean
  onChange: (id: T) => void
}) {
  return <div>
    <p className="goal-chip"><b>{label}</b></p>
    <div className="providers" role="radiogroup" aria-label={label}>
      {options.map((option) => <button
        key={option.id}
        type="button"
        role="radio"
        aria-checked={value === option.id}
        className={value === option.id ? 'is-on' : ''}
        disabled={disabled}
        onClick={() => onChange(option.id)}
      >{option.label}{option.badge ? <em>{option.badge}</em> : null}</button>)}
    </div>
  </div>
}

export function Dialog({
  title,
  description,
  locked,
  size = 'default',
  align,
  onClose,
  children,
}: {
  title: string
  description?: string
  locked?: boolean
  size?: 'default' | 'wide'
  align?: 'center' | 'start'
  onClose: () => void
  children: ReactNode
}) {
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => { if (event.key === 'Escape' && !locked) onClose() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [locked, onClose])
  return <div className={cx('overlay', align === 'start' && 'is-start')} role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget && !locked) onClose() }}>
    <div className={cx('dialog', size === 'wide' && 'is-wide')} role="dialog" aria-label={title}>
      <header>
        <div>
          <h2>{title}</h2>
          {description ? <p>{description}</p> : null}
        </div>
        <Button variant="icon" aria-label={copy.close} disabled={locked} onClick={onClose}><X size={14} /></Button>
      </header>
      {children}
    </div>
  </div>
}

export function Card({
  kicker,
  title,
  role,
  children,
}: {
  kicker?: string
  title?: string
  role?: 'alert' | 'status'
  children: ReactNode
}) {
  return <article className="card" role={role}>
    {kicker ? <small>{kicker}</small> : null}
    {title ? <h2>{title}</h2> : null}
    {children}
  </article>
}

export function StatusBadge({ state }: { state: ReviewState }) {
  return <span className={`status is-${state}`}><i />{statusCopy(state)}</span>
}

export function GoalChip({ label, value }: { label: string; value: string }) {
  if (!value.trim()) return null
  return <p className="goal-chip"><b>{label}</b>{value}</p>
}

export function ComposeBar({
  id,
  value,
  placeholder,
  submitLabel,
  minLength = 1,
  disabled,
  onChange,
  onSubmit,
}: {
  id?: string
  value: string
  placeholder: string
  submitLabel: ReactNode
  minLength?: number
  disabled?: boolean
  onChange: (value: string) => void
  onSubmit: () => void
}) {
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onSubmit()
  }
  return <form className="compose" onSubmit={submit}>
    <input id={id} value={value} placeholder={placeholder} disabled={disabled} onChange={(event) => onChange(event.currentTarget.value)} />
    <Button type="submit" disabled={disabled || value.trim().length < minLength}>{submitLabel}</Button>
  </form>
}

export function EmptyHint({ title, detail, icon }: { title: string; detail: string; icon: ReactNode }) {
  return <div className="empty">
    <span className="empty-mark" aria-hidden="true">{icon}</span>
    <strong>{title}</strong>
    <p>{detail}</p>
  </div>
}

export function Alert({ children }: { children: ReactNode }) {
  return <div className="alert" role="alert">{children}</div>
}
