import { useQuery } from '@tanstack/react-query'
import type { UseQueryResult } from '@tanstack/react-query'
import { apiClient } from './client'

export interface EditorialDigest {
  id: string       // YYYY-MM-DD
  date: string
  content: string  // markdown
  created_at: string
}

export interface WeeklyReport {
  id: string
  week_start: string
  content: string  // markdown
  created_at: string
}

export interface MonthlyReport {
  id: string
  month: string    // YYYY-MM
  content: string  // markdown
  created_at: string
}

export const reportKeys = {
  digests: (limit: number) => ['reports', 'digests', limit] as const,
  weekly: (limit: number) => ['reports', 'weekly', limit] as const,
  monthly: (limit: number) => ['reports', 'monthly', limit] as const,
}

// GET /api/reports/digests?limit=30
export function useDigests(limit = 30): UseQueryResult<EditorialDigest[]> {
  return useQuery({
    queryKey: reportKeys.digests(limit),
    queryFn: async () => {
      const { data } = await apiClient.get<EditorialDigest[]>('/api/reports/digests', {
        params: { limit },
      })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

// GET /api/reports/weekly?limit=8
export function useWeeklyReports(limit = 8): UseQueryResult<WeeklyReport[]> {
  return useQuery({
    queryKey: reportKeys.weekly(limit),
    queryFn: async () => {
      const { data } = await apiClient.get<WeeklyReport[]>('/api/reports/weekly', {
        params: { limit },
      })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}

// GET /api/reports/monthly?limit=6
export function useMonthlyReports(limit = 6): UseQueryResult<MonthlyReport[]> {
  return useQuery({
    queryKey: reportKeys.monthly(limit),
    queryFn: async () => {
      const { data } = await apiClient.get<MonthlyReport[]>('/api/reports/monthly', {
        params: { limit },
      })
      return data
    },
    staleTime: 5 * 60 * 1000,
  })
}
