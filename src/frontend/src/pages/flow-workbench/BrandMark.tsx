import { Waypoints } from 'lucide-react'

export function BrandMark({ className = '' }: { className?: string }) {
  return (
    <span className={`cf-brand-mark ${className}`.trim()} aria-hidden="true">
      <Waypoints />
    </span>
  )
}
