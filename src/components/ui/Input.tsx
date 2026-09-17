import type { InputHTMLAttributes } from 'react'

interface Props extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string | null
}

export function Input({ label, hint, error, className = '', id, ...rest }: Props) {
  const inputId = id ?? rest.name
  return (
    <label className="block" htmlFor={inputId}>
      {label && (
        <span className="mb-1.5 block text-sm font-medium text-ink-dim">{label}</span>
      )}
      <input
        id={inputId}
        className={`h-12 w-full rounded-xl border bg-surface-2 px-3.5 text-ink
          placeholder:text-ink-faint tabular
          ${error ? 'border-regressing' : 'border-line'}
          focus:border-accent focus:outline-none ${className}`}
        {...rest}
      />
      {error ? (
        <span className="mt-1.5 block text-sm text-regressing">{error}</span>
      ) : hint ? (
        <span className="mt-1.5 block text-sm text-ink-faint">{hint}</span>
      ) : null}
    </label>
  )
}
