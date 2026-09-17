import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'

export function History() {
  return (
    <>
      <PageHeader title="History" subtitle="Every session you have logged" />
      <EmptyState
        title="Nothing logged yet"
        body="Finished workouts land here, with every set exactly as you recorded it."
      />
    </>
  )
}
