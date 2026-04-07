import { usePosts } from '../api/posts'
import { PostQueue } from '../components/posts/PostQueue'
import { PipelineStatusBar } from '../components/pipeline/PipelineStatusBar'
import { TriggerButton } from '../components/pipeline/TriggerButton'
import { Badge } from '../components/common/Badge'
import { formatDistanceToNow } from 'date-fns'
import { usePipelineStatus } from '../api/pipeline'

export function QueuePage() {
  const { data: posts = [], isLoading: postsLoading } = usePosts('pending_review')
  const { data: pipelineStatus } = usePipelineStatus()
  const pendingCount = posts.length

  const lastRunAt = pipelineStatus?.last_run_at
    ? formatDistanceToNow(new Date(pipelineStatus.last_run_at), { addSuffix: true })
    : null

  return (
    <div className="min-h-screen bg-gray-950">
      {/* Header */}
      <div className="bg-gray-900/50 border-b border-gray-800 px-4 sm:px-6 py-6 sticky top-0 z-20">
        <div className="max-w-7xl mx-auto flex items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <h1 className="text-2xl sm:text-3xl font-bold text-gray-100">Post Queue</h1>
            {!postsLoading && (
              <Badge variant="neutral">{pendingCount}</Badge>
            )}
          </div>
          <TriggerButton />
        </div>
      </div>

      {/* Pipeline Status Bar */}
      <PipelineStatusBar />

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">
        {pendingCount === 0 && !postsLoading ? (
          <div className="card p-12 text-center space-y-4">
            <p className="text-6xl">📭</p>
            <h2 className="text-xl font-semibold text-gray-200">No posts in queue</h2>
            <p className="text-gray-400 text-sm max-w-sm mx-auto">
              The next pipeline run will generate new posts.
            </p>
            {lastRunAt && (
              <p className="text-gray-500 text-xs pt-4">
                Last run {lastRunAt}
              </p>
            )}
          </div>
        ) : (
          <PostQueue status="pending_review" />
        )}
      </main>
    </div>
  )
}
