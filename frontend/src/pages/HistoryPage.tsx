import { useMemo } from 'react'
import { format } from 'date-fns'
import { toZonedTime } from 'date-fns-tz'
import { usePosts, type Post } from '../api/posts'

const PHT = 'Asia/Manila'

function formatPHT(iso: string) {
  return format(toZonedTime(new Date(iso), PHT), 'MMM d, yyyy · h:mm a')
}

function truncate(text: string, max: number) {
  return text.length <= max ? text : text.slice(0, max) + '…'
}

// ─── Skeleton rows ────────────────────────────────────────────────────────────

function SkeletonRow() {
  return (
    <tr className="border-b border-gray-800">
      {[40, 200, 60, 120, 140, 60].map((w, i) => (
        <td key={i} className="px-4 py-3">
          <div className={`h-4 bg-gray-800 rounded animate-pulse`} style={{ width: w }} />
        </td>
      ))}
    </tr>
  )
}

function SkeletonCard() {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 space-y-3 animate-pulse">
      <div className="flex gap-3">
        <div className="w-10 h-10 rounded bg-gray-800 flex-shrink-0" />
        <div className="flex-1 space-y-2">
          <div className="h-3 bg-gray-800 rounded w-3/4" />
          <div className="h-3 bg-gray-800 rounded w-1/2" />
        </div>
      </div>
      <div className="h-3 bg-gray-800 rounded w-1/3" />
    </div>
  )
}

// ─── Desktop table row ────────────────────────────────────────────────────────

function PostTableRow({ post }: { post: Post }) {
  const publishedAt = post.publishing.published_at
  const fbId = post.publishing.facebook_post_id

  return (
    <tr className="border-b border-gray-800 hover:bg-gray-900/50 transition-colors">
      {/* Thumbnail */}
      <td className="px-4 py-3">
        <div className="w-10 h-10 rounded overflow-hidden bg-gray-800 flex-shrink-0">
          {post.image.storage_url ? (
            <img
              src={post.image.storage_url}
              alt=""
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-600 text-[10px]">
              —
            </div>
          )}
        </div>
      </td>

      {/* Text + strategy */}
      <td className="px-4 py-3 max-w-xs">
        <p className="text-gray-200 text-sm leading-snug">
          {truncate(post.content.full_text || post.content.body, 100)}
        </p>
        {post.editorial_strategy && (
          <span className="inline-block mt-1 px-2 py-0.5 rounded-full text-[10px] bg-blue-900/60 text-blue-300 border border-blue-700">
            {post.editorial_strategy}
          </span>
        )}
      </td>

      {/* Alignment score — posts API doesn't expose this yet; show urgency instead */}
      <td className="px-4 py-3 text-center">
        <span className={`text-sm font-semibold ${
          post.urgency === 'hot' ? 'text-red-400'
          : post.urgency === 'warm' ? 'text-orange-400'
          : 'text-blue-400'
        }`}>
          {post.urgency}
        </span>
      </td>

      {/* Published at */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-gray-400 text-xs">
          {publishedAt ? formatPHT(publishedAt) : '—'}
        </span>
      </td>

      {/* Engagement */}
      <td className="px-4 py-3 whitespace-nowrap">
        <span className="text-gray-400 text-xs space-x-2">
          <span>👍 {post.metrics.likes}</span>
          <span>💬 {post.metrics.comments}</span>
          <span>🔄 {post.metrics.shares}</span>
        </span>
      </td>

      {/* Facebook link */}
      <td className="px-4 py-3 text-center">
        {fbId ? (
          <a
            href={`https://www.facebook.com/${fbId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 text-xs underline underline-offset-2 transition-colors"
          >
            View
          </a>
        ) : (
          <span className="text-gray-700 text-xs">—</span>
        )}
      </td>
    </tr>
  )
}

// ─── Mobile card ──────────────────────────────────────────────────────────────

function PostMobileCard({ post }: { post: Post }) {
  const publishedAt = post.publishing.published_at
  const fbId = post.publishing.facebook_post_id

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4">
      <div className="flex gap-3 mb-3">
        {/* Thumbnail */}
        <div className="w-10 h-10 rounded overflow-hidden bg-gray-800 flex-shrink-0">
          {post.image.storage_url ? (
            <img src={post.image.storage_url} alt="" className="w-full h-full object-cover" />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-600 text-[10px]">—</div>
          )}
        </div>

        {/* Text */}
        <div className="flex-1 min-w-0">
          <p className="text-gray-200 text-sm leading-snug">
            {truncate(post.content.full_text || post.content.body, 100)}
          </p>
          {publishedAt && (
            <p className="text-gray-500 text-xs mt-1">{formatPHT(publishedAt)}</p>
          )}
        </div>
      </div>

      {/* Metrics row */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span className="space-x-2">
          <span>👍 {post.metrics.likes}</span>
          <span>💬 {post.metrics.comments}</span>
          <span>🔄 {post.metrics.shares}</span>
        </span>
        {fbId && (
          <a
            href={`https://www.facebook.com/${fbId}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-blue-400 hover:text-blue-300 underline underline-offset-2 transition-colors"
          >
            View on Facebook
          </a>
        )}
      </div>
    </div>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export function HistoryPage() {
  const { data: published = [], isLoading: loadingPublished } = usePosts('published')
  const { data: synced = [], isLoading: loadingSynced } = usePosts('metrics_synced')

  const loading = loadingPublished || loadingSynced

  // Merge and sort by published_at descending
  const posts = useMemo<Post[]>(() => {
    const seen = new Set<string>()
    const merged = [...published, ...synced].filter((p) => {
      if (seen.has(p.id)) return false
      seen.add(p.id)
      return true
    })
    return merged.sort((a, b) => {
      const ta = a.publishing.published_at ? new Date(a.publishing.published_at).getTime() : 0
      const tb = b.publishing.published_at ? new Date(b.publishing.published_at).getTime() : 0
      return tb - ta
    })
  }, [published, synced])

  return (
    <div className="space-y-6">
      {/* Page header */}
      <div className="flex items-baseline gap-3">
        <h1 className="text-white text-2xl font-bold">History</h1>
        {!loading && (
          <span className="text-gray-500 text-sm">{posts.length} post{posts.length !== 1 ? 's' : ''}</span>
        )}
      </div>

      {/* ── Desktop table (hidden on mobile) ── */}
      <div className="hidden sm:block overflow-x-auto rounded-xl border border-gray-800">
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-800 bg-gray-900/80">
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide">Image</th>
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide">Post</th>
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide text-center">Urgency</th>
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide">Published (PHT)</th>
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide">Engagement</th>
              <th className="px-4 py-3 text-gray-500 text-xs font-medium uppercase tracking-wide text-center">Link</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 5 }).map((_, i) => <SkeletonRow key={i} />)
            ) : posts.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-16 text-center text-gray-500 text-sm">
                  No published posts yet.
                </td>
              </tr>
            ) : (
              posts.map((post) => <PostTableRow key={post.id} post={post} />)
            )}
          </tbody>
        </table>
      </div>

      {/* ── Mobile card list (shown on mobile only) ── */}
      <div className="sm:hidden space-y-3">
        {loading ? (
          Array.from({ length: 5 }).map((_, i) => <SkeletonCard key={i} />)
        ) : posts.length === 0 ? (
          <p className="text-center text-gray-500 text-sm py-16">No published posts yet.</p>
        ) : (
          posts.map((post) => <PostMobileCard key={post.id} post={post} />)
        )}
      </div>
    </div>
  )
}
