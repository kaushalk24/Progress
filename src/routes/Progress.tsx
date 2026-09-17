import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'
import { Card } from '../components/ui/Card'

export function Progress() {
  return (
    <>
      <PageHeader title="Progress" subtitle="Which lifts are moving, and which are not" />

      <Card className="mb-4">
        <h2 className="text-sm font-semibold">How a stall gets called</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-dim">
          Progress means <span className="text-ink">more reps at the same weight</span>, or{' '}
          <span className="text-ink">more weight</span>. Nothing else counts — an extra set
          is more work, but it is not progress, and matching your best is not beating it.
        </p>
        <p className="mt-3 text-sm leading-relaxed text-ink-dim">
          Once a lift goes three sessions without a new best, it gets flagged here along
          with the exact number to beat next time.
        </p>
      </Card>

      <EmptyState
        title="Not enough data yet"
        body="Log the same exercise across a few sessions and its trend shows up here."
      />
    </>
  )
}
