import { useState } from 'react'
import type { FormEvent } from 'react'
import { supabase } from '../../lib/supabase'
import { Button } from '../../components/ui/Button'
import { Input } from '../../components/ui/Input'
import { Spinner } from '../../components/ui/Spinner'

type Mode = 'signin' | 'signup'

export function LoginPage() {
  const [mode, setMode] = useState<Mode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  async function onSubmit(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError(null)
    setNotice(null)

    const fn =
      mode === 'signin'
        ? supabase.auth.signInWithPassword({ email, password })
        : supabase.auth.signUp({ email, password })

    const { data, error: err } = await fn
    setBusy(false)

    if (err) {
      setError(err.message)
      return
    }
    // With email confirmation enabled, signUp returns a user but no session.
    if (mode === 'signup' && !data.session) {
      setNotice('Check your email to confirm your account, then sign in.')
    }
  }

  return (
    <div className="flex min-h-dvh flex-col justify-center px-6 pb-safe pt-safe">
      <div className="mx-auto w-full max-w-sm">
        <div className="mb-10">
          <h1 className="text-3xl font-bold tracking-tight">Progress</h1>
          <p className="mt-2 text-sm leading-relaxed text-ink-dim">
            Every set, every rep, every kilo — and an honest answer when a lift stops moving.
          </p>
        </div>

        <form onSubmit={onSubmit} className="space-y-4">
          <Input
            label="Email"
            name="email"
            type="email"
            inputMode="email"
            autoComplete="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
          />
          <Input
            label="Password"
            name="password"
            type="password"
            autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
            required
            minLength={6}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="At least 6 characters"
            error={error}
          />

          {notice && (
            <p className="rounded-xl border border-progressing/30 bg-progressing/10 px-3.5 py-3 text-sm text-progressing">
              {notice}
            </p>
          )}

          <Button type="submit" size="lg" full disabled={busy}>
            {busy ? <Spinner /> : mode === 'signin' ? 'Sign in' : 'Create account'}
          </Button>
        </form>

        <button
          type="button"
          className="mt-6 w-full text-center text-sm text-ink-dim hover:text-ink"
          onClick={() => {
            setMode(mode === 'signin' ? 'signup' : 'signin')
            setError(null)
            setNotice(null)
          }}
        >
          {mode === 'signin'
            ? "No account yet? Create one"
            : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}
