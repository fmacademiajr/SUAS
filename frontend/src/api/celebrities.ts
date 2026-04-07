import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface Celebrity {
  id: string
  name: string
  search_aliases: string[]
  platforms: string[]
  active: boolean
  notes?: string
}

export const celebrityKeys = {
  all: ['celebrities'] as const,
}

export function useCelebrities() {
  return useQuery({
    queryKey: celebrityKeys.all,
    queryFn: async () => {
      const { data } = await apiClient.get<Celebrity[]>('/api/celebrities')
      return data
    },
  })
}

export function useAddCelebrity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; search_aliases: string[]; platforms: string[]; notes?: string }) =>
      apiClient.post('/api/celebrities', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: celebrityKeys.all }),
  })
}

export function useToggleCelebrity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiClient.patch(`/api/celebrities/${id}`, { active }),
    onSuccess: () => qc.invalidateQueries({ queryKey: celebrityKeys.all }),
  })
}

export function useDeleteCelebrity() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => apiClient.delete(`/api/celebrities/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: celebrityKeys.all }),
  })
}
