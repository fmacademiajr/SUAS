import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from './client'

export interface VoiceGuide {
  persona_description: string
  tone_rules: string[]
  one_liner_patterns: string[]
  forbidden_phrases: string[]
  example_posts: string[]
}

export function useVoiceGuide() {
  return useQuery({
    queryKey: ['settings', 'voice-guide'],
    queryFn: async () => {
      const { data } = await apiClient.get<VoiceGuide>('/api/settings/voice-guide')
      return data
    },
  })
}

export function useUpdateVoiceGuide() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (guide: Partial<VoiceGuide>) =>
      apiClient.patch('/api/settings/voice-guide', guide),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings', 'voice-guide'] })
    },
  })
}
