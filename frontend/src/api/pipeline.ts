import { useQuery, useMutation } from '@tanstack/react-query'
import { apiClient } from './client'

export interface PipelineStatus {
  running: boolean
  last_run_id: string | null
  last_run_at: string | null
  last_error: string | null
}

export function usePipelineStatus() {
  return useQuery({
    queryKey: ['pipeline', 'status'],
    queryFn: async () => {
      const { data } = await apiClient.get<PipelineStatus>('/api/pipeline/status')
      return data
    },
    refetchInterval: 30_000,   // poll every 30s
  })
}

export function useTriggerPipeline() {
  return useMutation({
    mutationFn: ({
      slot = 'manual',
      dryRun = false,
    }: {
      slot?: string
      dryRun?: boolean
    }) =>
      apiClient.post('/api/pipeline/trigger', { slot, dry_run: dryRun }),
  })
}
