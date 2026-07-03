import { useMutation } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

export function useVoice() {
  const speak = useMutation({
    mutationFn: ({ text, sessionId }: { text: string; sessionId?: string }) =>
      api.voice.speak(text, sessionId),
  })

  const command = useMutation({
    mutationFn: ({ file, sessionId }: { file: Blob; sessionId?: string }) =>
      api.voice.command(file, sessionId),
  })

  const transcribe = useMutation({
    mutationFn: ({ file, sessionId }: { file: Blob; sessionId?: string }) =>
      api.voice.transcribe(file, sessionId),
  })

  return { speak, command, transcribe }
}
