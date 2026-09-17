import { useQuery } from '@tanstack/react-query'
import { supabase } from '../lib/supabase'
import { useAuth } from '../features/auth/AuthProvider'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/ui/Card'
import { Button } from '../components/ui/Button'
import { Spinner } from '../components/ui/Spinner'

function greeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'Good morning'
  if (h < 18) return 'Good afternoon'
  return 'Good evening'
}

export function Today() {
  const { profile } = useAuth()

  // Doubles as the deployment smoke test: a successful count proves the whole
  // chain works - env vars, auth token, RLS policy, and the seeded library.
  const libraryCount = useQuery({
    queryKey: ['exercise-count'],
    queryFn: async () => {
      const { count, error } = await supabase
        .from('exercises')
        .select('*', { count: 'exact', head: true })
      if (error) throw error
      return count ?? 0
    },
  })

  const name = profile?.display_name
  const today = new Date().toLocaleDateString(undefined, {
    weekday: 'long',
    day: 'numeric',
    month: 'long',
  })

  return (
    <>
      <PageHeader title={name ? `${greeting()}, ${name}` : greeting()} subtitle={today} />

      <Card className="mb-4">
        <h2 className="font-semibold">Ready to train</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-dim">
          Pick a routine like Leg Day or Chest Day, or start an empty session and add
          lifts as you go.
        </p>
        <Button className="mt-4" size="lg" full disabled>
          Start workout
        </Button>
        <p className="mt-2 text-center text-xs text-ink-faint">
          Logging arrives in the next slice
        </p>
      </Card>

      <Card>
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0">
            <h2 className="text-sm font-semibold">Exercise library</h2>
            <p className="mt-0.5 text-sm text-ink-dim">
              {libraryCount.isPending ? (
                'Checking connection…'
              ) : libraryCount.isError ? (
                <span className="text-regressing">
                  Could not reach the database. Check your Supabase settings.
                </span>
              ) : (
                <>
                  <span className="tabular font-medium text-ink">{libraryCount.data}</span>{' '}
                  exercises ready to use
                </>
              )}
            </p>
          </div>
          {libraryCount.isPending && <Spinner />}
        </div>
      </Card>
    </>
  )
}
