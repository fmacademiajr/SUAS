import { Outlet } from 'react-router-dom'
import { Sidebar } from './Sidebar'
import { BottomNav } from './BottomNav'
import { TopBar } from './TopBar'

export function AppShell() {
  return (
    <div className="min-h-screen bg-gray-950 flex">
      {/* Desktop sidebar — hidden on mobile */}
      <div className="hidden md:flex md:w-56 md:flex-col md:fixed md:inset-y-0">
        <Sidebar />
      </div>

      {/* Main content area */}
      <div className="flex-1 md:ml-56 flex flex-col min-h-screen">
        <TopBar />
        <main className="flex-1 p-4 md:p-6 pb-24 md:pb-6">
          <Outlet />
        </main>
      </div>

      {/* Mobile bottom nav — shown only on mobile */}
      <div className="md:hidden">
        <BottomNav />
      </div>
    </div>
  )
}
