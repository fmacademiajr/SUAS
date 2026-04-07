import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface ModelStatus {
  has_active_model: boolean
  model_version?: string
  r_squared?: number
  training_set_size?: number
  trained_at?: string
  gcs_path?: string
  top_features?: Array<{ name: string; importance: number }>
}

export interface OverrideRecord {
  post_id: string
  fernando_rating: number
  predicted_engagement: number
  normalized_rating: number
  normalized_pred: number
  divergence: number
  logged_at: string
}

export interface PostCount {
  eligible_posts: number
  threshold: number
  ready_to_train: boolean
}

export const modelAdminKeys = {
  status: ['model-admin', 'status'] as const,
  overrides: (limit: number) => ['model-admin', 'overrides', limit] as const,
  postCount: ['model-admin', 'post-count'] as const,
}

export function useModelStatus() {
  return useQuery({
    queryKey: modelAdminKeys.status,
    queryFn: async () => {
      const { data } = await apiClient.get<ModelStatus>('/api/model-admin/status')
      return data
    },
    staleTime: 60_000,
  })
}

export function useModelOverrides(limit = 20) {
  return useQuery({
    queryKey: modelAdminKeys.overrides(limit),
    queryFn: async () => {
      const { data } = await apiClient.get<OverrideRecord[]>('/api/model-admin/overrides', { params: { limit } })
      return data
    },
    staleTime: 2 * 60_000,
  })
}

export function usePostCount() {
  return useQuery({
    queryKey: modelAdminKeys.postCount,
    queryFn: async () => {
      const { data } = await apiClient.get<PostCount>('/api/model-admin/post-count')
      return data
    },
    staleTime: 60_000,
  })
}

export function useTriggerTraining() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => apiClient.post('/api/model-admin/train'),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: modelAdminKeys.status })
      qc.invalidateQueries({ queryKey: modelAdminKeys.postCount })
    },
  })
}
