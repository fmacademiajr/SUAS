import { useState, useEffect } from 'react'
import type { Post } from '../../api/posts'
import { useUpdatePost } from '../../api/posts'

interface EditModalProps {
  post: Post
  onClose: () => void
}

export function EditModal({ post, onClose }: EditModalProps) {
  const [oneLiner, setOneLiner] = useState(post.content.one_liner)
  const [body, setBody] = useState(post.content.body)
  const [hashtags, setHashtags] = useState(post.content.hashtags.join(' '))
  const update = useUpdatePost()

  const handleSave = () => {
    update.mutate({
      postId: post.id,
      updates: {
        one_liner: oneLiner,
        body,
        hashtags: hashtags.split(/\s+/).filter(t => t.startsWith('#')),
      },
    }, { onSuccess: onClose })
  }

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-end md:items-center justify-center p-0 md:p-4" onClick={onClose}>
      <div
        className="w-full md:max-w-xl bg-gray-900 border border-gray-700 rounded-t-2xl md:rounded-2xl p-5 space-y-4 max-h-[90vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h3 className="font-semibold text-gray-100">Edit Post</h3>
          <button onClick={onClose} className="text-gray-500 hover:text-gray-300 min-h-[44px] min-w-[44px] flex items-center justify-center">✕</button>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-400 font-medium">One-liner (≤10 words)</label>
          <input value={oneLiner} onChange={e => setOneLiner(e.target.value)} className="input" />
          <p className="text-xs text-gray-600">{oneLiner.split(/\s+/).filter(Boolean).length} / 10 words</p>
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-400 font-medium">Body</label>
          <textarea value={body} onChange={e => setBody(e.target.value)} rows={5} className="input resize-none" />
        </div>

        <div className="space-y-1">
          <label className="text-xs text-gray-400 font-medium">Hashtags (space-separated)</label>
          <input value={hashtags} onChange={e => setHashtags(e.target.value)} className="input" placeholder="#ShutUpAndServe #Philippines" />
        </div>

        <div className="flex gap-2 pt-1">
          <button onClick={handleSave} disabled={update.isPending} className="btn-primary flex-1 min-h-[44px]">
            {update.isPending ? 'Saving...' : 'Save Changes'}
          </button>
          <button onClick={onClose} className="btn-secondary min-h-[44px] px-5">Cancel</button>
        </div>
      </div>
    </div>
  )
}
