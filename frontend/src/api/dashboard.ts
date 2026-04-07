import { useQuery } from '@tanstack/react-query'
import { apiClient } from './client'

export interface DashboardStats {
  post_counts: {
    pending_review: number
    approved: number
    published: number
    rejected: number
    metrics_synced: number
  }
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ['dashboard', 'stats'],
    queryFn: async () => {
      const { data } = await apiClient.get<DashboardStats>('/api/dashboard/stats')
      return data
    },
    refetchInterval: 60_000,   // poll every 60s
  })
}

export interface EngagementDataPoint {
  date: string   // "2026-04-01"
  likes: number
  comments: number
  shares: number
}

export interface ScoreDistributionPoint {
  score: number
  count: number
}

export function useEngagementData(days = 30) {
  return useQuery({
    queryKey: ['dashboard', 'engagement', days],
    queryFn: async () => {
      const { data } = await apiClient.get<EngagementDataPoint[]>('/api/dashboard/engagement', { params: { days } })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

export function useScoreDistribution(days = 30) {
  return useQuery({
    queryKey: ['dashboard', 'score-distribution', days],
    queryFn: async () => {
      const { data } = await apiClient.get<ScoreDistributionPoint[]>('/api/dashboard/score-distribution', { params: { days } })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}
