import { NavLink } from 'react-router-dom'
import { useAuth } from '../../auth/AuthContext'
import clsx from 'clsx'

const NAV_ITEMS = [
  { to: '/queue', label: 'Review Queue', icon: '📋' },
  { to: '/dashboard', label: 'Dashboard', icon: '📊' },
  { to: '/history', label: 'Published', icon: '📰' },
  { to: '/reports', label: 'Reports', icon: '📈' },
  { to: '/settings', label: 'Settings', icon: '⚙️' },
]

export function Sidebar() {
  const { signOut, user } = useAuth()

  return (
    <div className="flex flex-col h-full bg-gray-900 border-r border-gray-800">
      {/* Brand */}
      <div className="px-4 py-5 border-b border-gray-800">
        <h1 className="text-lg font-black tracking-widest text-white">SUAS</h1>
        <p className="text-xs text-gray-500 tracking-widest">SHUT UP AND SERVE</p>
      </div>

      {/* Nav links */}
      <nav className="flex-1 px-3 py-4 space-y-1">
        {NAV_ITEMS.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              clsx(
                'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                isActive
                  ? 'bg-blue-600 text-white'
                  : 'text-gray-400 hover:text-gray-200 hover:bg-gray-800'
              )
            }
          >
            <span>{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      {/* User + sign out */}
      <div className="px-3 py-4 border-t border-gray-800">
        <p className="text-xs text-gray-500 px-3 mb-2 truncate">{user?.email}</p>
        <button
          onClick={signOut}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
        >
          <span>🚪</span>
          Sign out
        </button>
      </div>
    </div>
  )
}
