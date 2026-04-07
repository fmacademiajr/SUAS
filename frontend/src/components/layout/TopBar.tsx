import { useLocation } from 'react-router-dom'
import { usePosts } from '../../api/posts'

const PAGE_TITLES: Record<string, string> = {
  '/queue': 'Review Queue',
  '/dashboard': 'Dashboard',
  '/history': 'Published',
  '/reports': 'Reports',
  '/settings': 'Settings',
}

export function TopBar() {
  const location = useLocation()
  const title = PAGE_TITLES[location.pathname] ?? 'SUAS'
  const { data: pendingPosts } = usePosts('pending_review')
  const pendingCount = pendingPosts?.length ?? 0

  return (
    <header className="sticky top-0 z-10 bg-gray-900/95 backdrop-blur border-b border-gray-800 px-4 py-3 flex items-center justify-between md:hidden">
      <div className="flex items-center gap-2">
        <span className="font-black tracking-widest text-white text-sm">SUAS</span>
        <span className="text-gray-600">·</span>
        <span className="text-gray-300 text-sm font-medium">{title}</span>
      </div>
      {pendingCount > 0 && (
        <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-600 text-white text-xs font-bold">
          {pendingCount > 99 ? '99+' : pendingCount}
        </span>
      )}
    </header>
  )
}
