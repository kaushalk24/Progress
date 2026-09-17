import type { ReactNode } from 'react'

export function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon?: ReactNode
  title: string
  body?: string
  action?: ReactNode
}) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <div className="mb-4 text-ink-faint">{icon}</div>}
      <h2 className="text-lg font-semibold text-ink">{title}</h2>
      {body && <p className="mt-2 max-w-xs text-sm leading-relaxed text-ink-dim">{body}</p>}
      {action && <div className="mt-6">{action}</div>}
    </div>
  )
}
