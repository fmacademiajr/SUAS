import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface Post {
  id: string
  status: 'pending_review' | 'approved' | 'rejected' | 'published' | 'metrics_synced'
  post_type: 'news' | 'amplify' | 'springboard' | 'link_drop'
  urgency: 'hot' | 'warm' | 'cool'
  editorial_strategy: string | null
  content: {
    one_liner: string
    body: string
    hashtags: string[]
    full_text: string
  }
  image: {
    prompt: string
    storage_url: string | null
    gcs_path: string | null
    generation_model: string
  }
  publishing: {
    scheduled_for: string | null
    approved_at: string | null
    published_at: string | null
    facebook_post_id: string | null
  }
  metrics: {
    likes: number
    comments: number
    shares: number
    reach: number
  }
  source_description: string | null
  legal_review_required: boolean
  created_at: string
  updated_at: string
}

// Query keys
export const postKeys = {
  all: ['posts'] as const,
  list: (status?: string) => [...postKeys.all, 'list', status] as const,
  detail: (id: string) => [...postKeys.all, 'detail', id] as const,
}

// Fetch posts by status
export function usePosts(status?: string) {
  return useQuery({
    queryKey: postKeys.list(status),
    queryFn: async () => {
      const params = status ? { status } : {}
      const { data } = await apiClient.get<Post[]>('/api/posts', { params })
      return data
    },
  })
}

// Fetch single post
export function usePost(id: string) {
  return useQuery({
    queryKey: postKeys.detail(id),
    queryFn: async () => {
      const { data } = await apiClient.get<Post>(`/api/posts/${id}`)
      return data
    },
    enabled: !!id,
  })
}

// Approve a post
export function useApprovePost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (postId: string) => apiClient.post(`/api/posts/${postId}/approve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: postKeys.all })
    },
  })
}

// Reject a post
export function useRejectPost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ postId, reason }: { postId: string; reason: string }) =>
      apiClient.post(`/api/posts/${postId}/reject`, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: postKeys.all })
    },
  })
}

// Update post content (edit)
export function useUpdatePost() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      postId,
      updates,
    }: {
      postId: string
      updates: { one_liner?: string; body?: string; hashtags?: string[]; image_prompt?: string }
    }) => apiClient.patch(`/api/posts/${postId}`, updates),
    onSuccess: (_data, { postId }) => {
      qc.invalidateQueries({ queryKey: postKeys.detail(postId) })
      qc.invalidateQueries({ queryKey: postKeys.list() })
    },
  })
}
