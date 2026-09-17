import { PageHeader } from '../components/PageHeader'
import { EmptyState } from '../components/ui/EmptyState'

export function Routines() {
  return (
    <>
      <PageHeader title="Routines" subtitle="Your training days" />
      <EmptyState
        title="No routines yet"
        body="Build a Leg Day or a Chest Day, pick the exercises that belong in it, and add your own lift if it is not in the library."
      />
    </>
  )
}
