import { useState } from 'react'
import type { ReactNode } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../features/auth/AuthProvider'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'
import type { EffortDisplay, Profile, Unit } from '../lib/types'

function SegmentedControl<T extends string>({
  value,
  options,
  onChange,
  disabled,
}: {
  value: T
  options: ReadonlyArray<{ value: T; label: string }>
  onChange: (v: T) => void
  disabled?: boolean
}) {
  return (
    <div className="inline-flex rounded-xl border border-line bg-surface-2 p-1">
      {options.map((opt) => (
        <button
          key={opt.value}
          type="button"
          disabled={disabled}
          onClick={() => onChange(opt.value)}
          className={`h-9 min-w-16 rounded-lg px-3 text-sm font-medium transition-colors
            disabled:opacity-40 ${
              value === opt.value
                ? 'bg-accent text-black'
                : 'text-ink-dim hover:text-ink'
            }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  )
}

function Row({
  label,
  hint,
  children,
}: {
  label: string
  hint?: string
  children: ReactNode
}) {
  return (
    <div className="flex items-center justify-between gap-4 py-3.5">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-relaxed text-ink-faint">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  )
}

export function Settings() {
  const { profile, user, refreshProfile, signOut } = useAuth()
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function patch(changes: Partial<Profile>) {
    if (!user) return
    setSaving(true)
    setError(null)
    const { error: err } = await supabase.from('profiles').update(changes).eq('id', user.id)
    if (err) setError(err.message)
    else await refreshProfile()
    setSaving(false)
  }

  if (!profile) {
    return (
      <>
        <PageHeader title="Settings" />
        <div className="flex justify-center py-12">
          <Spinner />
        </div>
      </>
    )
  }

  return (
    <>
      <PageHeader title="Settings" subtitle={user?.email ?? undefined} />

      <Card className="mb-4 divide-y divide-line py-0">
        <Row label="Units" hint="Weights are always stored in kg and converted for display">
          <SegmentedControl<Unit>
            value={profile.unit}
            disabled={saving}
            onChange={(unit) => void patch({ unit })}
            options={[
              { value: 'kg', label: 'kg' },
              { value: 'lb', label: 'lb' },
            ]}
          />
        </Row>

        <Row label="Effort scale" hint="RPE 8 and 2 reps in reserve are the same thing">
          <SegmentedControl<EffortDisplay>
            value={profile.effort_display}
            disabled={saving}
            onChange={(effort_display) => void patch({ effort_display })}
            options={[
              { value: 'rir', label: 'RIR' },
              { value: 'rpe', label: 'RPE' },
            ]}
          />
        </Row>

        <Row label="Default rest" hint="Starting point for the timer between sets">
          <SegmentedControl<string>
            value={String(profile.default_rest_seconds)}
            disabled={saving}
            onChange={(v) => void patch({ default_rest_seconds: Number(v) })}
            options={[
              { value: '60', label: '60s' },
              { value: '90', label: '90s' },
              { value: '120', label: '2m' },
              { value: '180', label: '3m' },
            ]}
          />
        </Row>

        <Row
          label="Stall after"
          hint="Sessions without a new best before a lift is flagged as stalled"
        >
          <SegmentedControl<string>
            value={String(profile.stall_threshold_sessions)}
            disabled={saving}
            onChange={(v) => void patch({ stall_threshold_sessions: Number(v) })}
            options={[
              { value: '2', label: '2' },
              { value: '3', label: '3' },
              { value: '4', label: '4' },
              { value: '5', label: '5' },
            ]}
          />
        </Row>
      </Card>

      {error && (
        <p className="mb-4 rounded-xl border border-regressing/30 bg-regressing/10 px-3.5 py-3 text-sm text-regressing">
          {error}
        </p>
      )}

      <Button variant="danger" full onClick={() => void signOut()}>
        Sign out
      </Button>
    </>
  )
}
