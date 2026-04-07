import { useState } from 'react'
import { formatDistanceToNow } from 'date-fns'
import { toZonedTime, format } from 'date-fns-tz'
import clsx from 'clsx'
import type { Post } from '../../api/posts'
import { PostActions } from './PostActions'

const URGENCY_COLORS = {
  hot: 'bg-red-500/20 text-red-400 border-red-500/30',
  warm: 'bg-orange-500/20 text-orange-400 border-orange-500/30',
  cool: 'bg-blue-500/20 text-blue-400 border-blue-500/30',
}

const STRATEGY_LABELS = {
  ride_the_wave: '🌊 Ride the Wave',
  fill_the_gap: '🔍 Fill the Gap',
  connect_the_dots: '🔗 Connect the Dots',
}

interface PostCardProps {
  post: Post
}

export function PostCard({ post }: PostCardProps) {
  const [expanded, setExpanded] = useState(false)
  const PHT = 'Asia/Manila'

  const scheduledFor = post.publishing.scheduled_for
    ? format(toZonedTime(new Date(post.publishing.scheduled_for), PHT), 'EEE, MMM d · h:mm a', { timeZone: PHT })
    : null

  return (
    <div className={clsx(
      'card overflow-hidden transition-all duration-200',
      post.legal_review_required && 'ring-2 ring-yellow-500/50'
    )}>
      {/* Legal review warning */}
      {post.legal_review_required && (
        <div className="bg-yellow-500/10 border-b border-yellow-500/30 px-4 py-2 flex items-center gap-2">
          <span className="text-yellow-400 text-xs font-semibold">⚠️ LEGAL REVIEW REQUIRED — politician named directly</span>
        </div>
      )}

      {/* Image + header */}
      <div className="flex gap-3 p-4">
        {/* Post image thumbnail */}
        <div className="flex-shrink-0 w-24 h-24 md:w-32 md:h-32 rounded-lg overflow-hidden bg-gray-800">
          {post.image.storage_url ? (
            <img
              src={post.image.storage_url}
              alt="Post image"
              className="w-full h-full object-cover"
            />
          ) : (
            <div className="w-full h-full flex items-center justify-center text-gray-600 text-xs text-center p-2">
              Generating image...
            </div>
          )}
        </div>

        {/* Post content */}
        <div className="flex-1 min-w-0">
          {/* Badges row */}
          <div className="flex flex-wrap gap-1.5 mb-2">
            <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold border uppercase tracking-wide', URGENCY_COLORS[post.urgency])}>
              {post.urgency}
            </span>
            {post.editorial_strategy && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-gray-800 text-gray-400 border border-gray-700">
                {STRATEGY_LABELS[post.editorial_strategy as keyof typeof STRATEGY_LABELS] ?? post.editorial_strategy}
              </span>
            )}
            {post.post_type !== 'news' && (
              <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-purple-500/20 text-purple-400 border border-purple-500/30">
                {post.post_type}
              </span>
            )}
          </div>

          {/* One-liner */}
          <p className="text-white font-bold text-sm leading-tight mb-1.5 line-clamp-2">
            {post.content.one_liner}
          </p>

          {/* Body preview */}
          <p className="text-gray-400 text-xs leading-relaxed line-clamp-2">
            {post.content.body}
          </p>
        </div>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div className="px-4 pb-3 border-t border-gray-800 pt-3">
          <p className="text-gray-300 text-sm leading-relaxed mb-2">{post.content.body}</p>
          <p className="text-blue-400 text-xs">{post.content.hashtags.join(' ')}</p>
          {post.source_description && (
            <p className="text-gray-500 text-xs mt-2 italic">{post.source_description}</p>
          )}
        </div>
      )}

      {/* Footer: schedule + expand + actions */}
      <div className="px-4 pb-4 flex flex-col gap-3">
        <div className="flex items-center justify-between">
          {scheduledFor && (
            <span className="text-gray-500 text-xs">🕐 {scheduledFor} PHT</span>
          )}
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-gray-500 hover:text-gray-300 text-xs transition-colors ml-auto"
          >
            {expanded ? 'Show less ↑' : 'Show more ↓'}
          </button>
        </div>

        <PostActions post={post} />
      </div>
    </div>
  )
}
