import { useState } from 'react'
import clsx from 'clsx'
import type { Post } from '../../api/posts'
import { useApprovePost, useRejectPost } from '../../api/posts'

interface PostActionsProps {
  post: Post
  onEdit?: () => void
}

export function PostActions({ post, onEdit }: PostActionsProps) {
  const [showRejectInput, setShowRejectInput] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  const approve = useApprovePost()
  const reject = useRejectPost()

  const handleApprove = () => approve.mutate(post.id)

  const handleReject = () => {
    if (!rejectReason.trim()) return
    reject.mutate({ postId: post.id, reason: rejectReason })
    setShowRejectInput(false)
    setRejectReason('')
  }

  const isProcessing = approve.isPending || reject.isPending

  if (showRejectInput) {
    return (
      <div className="space-y-2">
        <input
          type="text"
          value={rejectReason}
          onChange={(e) => setRejectReason(e.target.value)}
          placeholder="Reason for rejecting..."
          className="input text-sm"
          autoFocus
          onKeyDown={(e) => e.key === 'Enter' && handleReject()}
        />
        <div className="flex gap-2">
          <button onClick={handleReject} disabled={!rejectReason.trim()} className="btn-danger flex-1 min-h-[44px]">
            Confirm Reject
          </button>
          <button onClick={() => setShowRejectInput(false)} className="btn-secondary min-h-[44px] px-4">
            Cancel
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="grid grid-cols-3 gap-2">
      <button
        onClick={handleApprove}
        disabled={isProcessing}
        className={clsx('btn-primary min-h-[44px] flex items-center justify-center gap-1.5', approve.isPending && 'opacity-60')}
      >
        {approve.isPending ? (
          <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
        ) : (
          <>✓ Approve</>
        )}
      </button>

      <button
        onClick={() => setShowRejectInput(true)}
        disabled={isProcessing}
        className="btn-danger min-h-[44px] flex items-center justify-center gap-1.5"
      >
        ✕ Reject
      </button>

      <button
        onClick={onEdit}
        disabled={isProcessing}
        className="btn-secondary min-h-[44px] flex items-center justify-center gap-1.5"
      >
        ✎ Edit
      </button>
    </div>
  )
}
