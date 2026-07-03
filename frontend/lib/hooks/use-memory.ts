import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export function useMemoryNodes(sessionId = 'default') {
  const conversationHistory = useQuery({
    queryKey: ['conversation', sessionId],
    queryFn: () => api.chat.history(sessionId),
  })

  const explanations = useQuery({
    queryKey: ['explanations'],
    queryFn: () => api.explain.query({ limit: 20 }),
  })

  const stats = useQuery({
    queryKey: ['system-stats'],
    queryFn: api.system.stats,
  })

  return {
    conversationHistory,
    explanations,
    stats,
    isLoading: conversationHistory.isLoading || explanations.isLoading,
    error: conversationHistory.error || explanations.error,
  }
}
