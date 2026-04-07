import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface LearningLogEntry {
  id: string
  week: string              // "2026-04-07 to 2026-04-13"
  generated_at: string      // ISO
  posts_analyzed: number
  top_insight: string
  confirmed_patterns: string[]
  disproven_assumptions: string[]
  adjustments: string[]
  experiment_for_next_week: string
  model_overrides_this_week: number
  fernando_rating?: number  // 1-5, set by Fernando
}

export const learningKeys = {
  all: ['learning-log'] as const,
  list: (limit: number) => [...learningKeys.all, limit] as const,
}

export function useLearningLog(limit = 20) {
  return useQuery({
    queryKey: learningKeys.list(limit),
    queryFn: async () => {
      const { data } = await apiClient.get<LearningLogEntry[]>('/api/learning-log', { params: { limit } })
      return data
    },
    staleTime: 2 * 60 * 1000,
  })
}

export function useRateLearningEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ entryId, rating }: { entryId: string; rating: number }) =>
      apiClient.patch(`/api/learning-log/${entryId}`, { fernando_rating: rating }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: learningKeys.all })
    },
  })
}
