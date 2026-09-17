import type { ButtonHTMLAttributes, ReactNode } from 'react'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger'
type Size = 'sm' | 'md' | 'lg'

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  full?: boolean
  children: ReactNode
}

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-accent text-black font-semibold hover:bg-accent/90 active:bg-accent/80',
  secondary: 'bg-surface-2 text-ink border border-line hover:bg-line active:bg-line',
  ghost: 'bg-transparent text-ink-dim hover:text-ink hover:bg-surface-2',
  danger: 'bg-transparent text-regressing border border-regressing/40 hover:bg-regressing/10',
}

// Minimum 44px tall throughout: this is tapped with a thumb, mid-set, and a
// missed tap costs more than the space a large button takes up.
const SIZES: Record<Size, string> = {
  sm: 'h-9 px-3 text-sm rounded-lg',
  md: 'h-11 px-4 text-[15px] rounded-xl',
  lg: 'h-14 px-6 text-base rounded-2xl',
}

export function Button({
  variant = 'primary',
  size = 'md',
  full = false,
  className = '',
  children,
  ...rest
}: Props) {
  return (
    <button
      className={`inline-flex items-center justify-center gap-2 transition-colors
        disabled:opacity-40 disabled:pointer-events-none select-none
        ${VARIANTS[variant]} ${SIZES[size]} ${full ? 'w-full' : ''} ${className}`}
      {...rest}
    >
      {children}
    </button>
  )
}
