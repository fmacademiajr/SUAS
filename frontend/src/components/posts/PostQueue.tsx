import { usePosts } from '../../api/posts'
import { PostCard } from './PostCard'

interface PostQueueProps {
  status?: string
  emptyMessage?: string
}

export function PostQueue({ status = 'pending_review', emptyMessage = 'No posts to review.' }: PostQueueProps) {
  const { data: posts, isLoading, error } = usePosts(status)

  if (isLoading) {
    return (
      <div className="space-y-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="card h-48 animate-pulse bg-gray-800/50" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="card p-6 text-center">
        <p className="text-red-400 text-sm">Failed to load posts. Make sure the backend is running.</p>
      </div>
    )
  }

  if (!posts || posts.length === 0) {
    return (
      <div className="card p-12 text-center">
        <p className="text-4xl mb-3">📭</p>
        <p className="text-gray-500 text-sm">{emptyMessage}</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {posts.map((post) => (
        <PostCard key={post.id} post={post} />
      ))}
    </div>
  )
}
