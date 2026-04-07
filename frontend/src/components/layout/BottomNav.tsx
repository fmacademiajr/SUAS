import { NavLink } from 'react-router-dom'
import { usePosts } from '../../api/posts'
import clsx from 'clsx'

const NAV_ITEMS = [
  { to: '/queue', label: 'Queue', icon: '📋' },
  { to: '/dashboard', label: 'Stats', icon: '📊' },
  { to: '/history', label: 'History', icon: '📰' },
  { to: '/reports', label: 'Reports', icon: '📈' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export function BottomNav() {
  const { data: pendingPosts } = usePosts('pending_review')
  const pendingCount = pendingPosts?.length ?? 0

  return (
    <nav className="fixed bottom-0 left-0 right-0 z-20 bg-gray-900/95 backdrop-blur border-t border-gray-800 safe-area-pb">
      <div className="flex">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex-1 flex flex-col items-center justify-center py-2 min-h-[56px] relative text-xs transition-colors',
                isActive ? 'text-blue-500' : 'text-gray-500'
              )
            }
          >
            <span className="text-lg leading-none">{icon}</span>
            <span className="mt-0.5">{label}</span>
            {to === '/queue' && pendingCount > 0 && (
              <span className="absolute top-1 right-1/4 translate-x-2 inline-flex items-center justify-center min-w-[18px] h-[18px] rounded-full bg-blue-600 text-white text-[10px] font-bold px-1">
                {pendingCount > 99 ? '99+' : pendingCount}
              </span>
            )}
          </NavLink>
        ))}
      </div>
    </nav>
  )
}
