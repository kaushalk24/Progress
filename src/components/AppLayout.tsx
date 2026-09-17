import { Outlet } from 'react-router-dom'
import { BottomNav } from './BottomNav'

export function AppLayout() {
  return (
    <div className="min-h-dvh bg-bg">
      {/* pb-28 clears the fixed bottom nav; pt-safe clears the notch. */}
      <main className="mx-auto max-w-lg px-4 pb-28 pt-safe">
        <Outlet />
      </main>
      <BottomNav />
    </div>
  )
}
