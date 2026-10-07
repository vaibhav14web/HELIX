'use client'

import { useState, useRef, useCallback, useEffect } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { Mic, MicOff, Volume2, VolumeX, Zap, Loader2, AlertTriangle, ShieldAlert } from 'lucide-react'
import { GlassCard } from '@/components/os/GlassCard'
import { useVoice } from '@/lib/hooks/use-voice'
import { usePermissions } from '@/lib/hooks/use-permissions'
import { useOSStore } from '@/lib/os-store'
import { api } from '@/lib/api-client'
import { cn } from '@/lib/utils'
import { cleanTextForSpeech } from '@/lib/speech-cleaner'

type VoiceState = 'idle' | 'listening' | 'processing' | 'speaking' | 'interrupted' | 'permission_pending'

interface TranscriptEntry {
  time: string
  speaker: 'User' | 'HELIX'
  text: string
}

const stateConfig: Record<VoiceState, { label: string; color: string; ringColor: string; icon?: React.ComponentType<{ className?: string }> }> = {
  idle: { label: 'Ready to Listen', color: 'text-zinc-500', ringColor: 'rgba(255,255,255,0.06)' },
  listening: { label: 'Listening...', color: 'text-[#00d4ff]', ringColor: 'rgba(0,212,255,0.3)' },
  processing: { label: 'Processing...', color: 'text-[#7c3aed]', ringColor: 'rgba(124,58,237,0.3)', icon: Loader2 },
  speaking: { label: 'HELIX Speaking', color: 'text-[#22c55e]', ringColor: 'rgba(34,197,94,0.3)' },
  interrupted: { label: 'Interrupted', color: 'text-[#ef4444]', ringColor: 'rgba(239,68,68,0.3)', icon: AlertTriangle },
  permission_pending: { label: 'Permission Pending', color: 'text-[#f59e0b]', ringColor: 'rgba(245,158,11,0.3)', icon: ShieldAlert },
}

function WaveformBar({ delay, active }: { delay: number; active: boolean }) {
  return (
    <motion.div
      className="w-1 rounded-full bg-[#00d4ff]"
      animate={active ? { scaleY: [0.2, 1, 0.4, 0.8, 0.2], opacity: [0.5, 1, 0.7, 1, 0.5] } : { scaleY: 0.2, opacity: 0.2 }}
      transition={active ? { duration: 0.8, repeat: Infinity, delay, ease: 'easeInOut' } : { duration: 0.3 }}
      style={{ height: 40, transformOrigin: 'center' }}
    />
  )
}

function WaveformVisualizer({ active, bars = 32 }: { active: boolean; bars?: number }) {
  return (
    <div className="flex items-center gap-0.5" style={{ height: 40 }}>
      {Array.from({ length: bars }, (_, i) => (
        <WaveformBar key={i} delay={(i / bars) * 0.6} active={active} />
      ))}
    </div>
  )
}

const voiceProfiles = [
  { name: 'ARIA', desc: 'Professional · English', active: true },
  { name: 'NOVA', desc: 'Warm · English UK', active: false },
  { name: 'ORION', desc: 'Deep · English US', active: false },
]

const shortcuts = [
  { key: 'Space', label: 'Hold to Talk' },
  { key: '⌘ +', label: 'Increase Volume' },
  { key: '⌘ −', label: 'Decrease Volume' },
  { key: 'Esc', label: 'Cancel' },
]

export function VoicePage() {
  const { speak, command } = useVoice()
  const { pending } = usePermissions()
  const { activeSessionId } = useOSStore()
  const pendingCount = pending.data?.pending?.length ?? 0

  const [voiceState, setVoiceState] = useState<VoiceState>('idle')
  const [muted, setMuted] = useState(false)
  const [volume, setVolume] = useState(80)
  const [transcript, setTranscript] = useState('')
  const [transcripts, setTranscripts] = useState<TranscriptEntry[]>([])
  const mediaRecorder = useRef<MediaRecorder | null>(null)
  const audioChunks = useRef<Blob[]>([])
  const currentAudioRef = useRef<HTMLAudioElement | null>(null)

  const handleInterrupt = useCallback(() => {
    if (currentAudioRef.current) {
      currentAudioRef.current.pause()
      currentAudioRef.current = null
    }
    api.voice.interrupt().catch(() => {})
    setVoiceState('interrupted')
    setTranscript('Interrupted by user')
    setTimeout(() => {
      setVoiceState('idle')
      setTranscript('')
    }, 1500)
  }, [])

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && voiceState === 'speaking') {
        handleInterrupt()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [voiceState, handleInterrupt])

  // Track permission pending transitions
  useEffect(() => {
    if (pendingCount > 0 && voiceState === 'idle') {
      setVoiceState('permission_pending')
    } else if (pendingCount === 0 && voiceState === 'permission_pending') {
      setVoiceState('idle')
    }
  }, [pendingCount, voiceState])

  const audioContextRef = useRef<AudioContext | null>(null)
  const animFrameRef = useRef<number | null>(null)
  const maxTimeoutRef = useRef<NodeJS.Timeout | null>(null)

  const stopAudioCapture = useCallback(() => {
    if (maxTimeoutRef.current) {
      clearTimeout(maxTimeoutRef.current)
      maxTimeoutRef.current = null
    }
    if (animFrameRef.current) {
      cancelAnimationFrame(animFrameRef.current)
      animFrameRef.current = null
    }
    if (audioContextRef.current) {
      try {
        audioContextRef.current.close()
      } catch {}
      audioContextRef.current = null
    }
  }, [])

  useEffect(() => {
    return () => {
      stopAudioCapture()
      if (currentAudioRef.current) {
        currentAudioRef.current.pause()
        currentAudioRef.current = null
      }
    }
  }, [stopAudioCapture])

  const toggle = useCallback(async () => {
    if (voiceState === 'speaking') {
      handleInterrupt()
      return
    }

    if (voiceState === 'listening') {
      // User manually stopped listening -> finish and process immediately
      stopAudioCapture()
      if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
        setVoiceState('processing')
        mediaRecorder.current.stop()
      }
      return
    }

    if (voiceState === 'idle' || voiceState === 'permission_pending') {
      stopAudioCapture()
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
        const recorder = new MediaRecorder(stream, { mimeType: 'audio/webm' })
        mediaRecorder.current = recorder
        audioChunks.current = []

        recorder.ondataavailable = (e) => {
          if (e.data.size > 0) audioChunks.current.push(e.data)
        }

        recorder.onstop = async () => {
          stopAudioCapture()
          stream.getTracks().forEach((t) => t.stop())
          const blob = new Blob(audioChunks.current, { type: 'audio/webm' })
          if (blob.size === 0) {
            setVoiceState('idle')
            return
          }

          setVoiceState('processing')
          try {
            const result = await command.mutateAsync({ file: blob, sessionId: activeSessionId })
            setTranscripts((prev) => [
              ...prev,
              { time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }), speaker: 'User', text: result.text || 'Voice command sent' },
            ])
            const playVoiceFallback = (text: string) => {
              const cleaned = cleanTextForSpeech(text)
              if (typeof window !== 'undefined' && 'speechSynthesis' in window && cleaned) {
                setVoiceState('speaking')
                window.speechSynthesis.cancel()
                const utterance = new SpeechSynthesisUtterance(cleaned)
                utterance.onend = () => setVoiceState('idle')
                utterance.onerror = () => setVoiceState('idle')
                window.speechSynthesis.speak(utterance)
              } else {
                setVoiceState('idle')
              }
            }

            if (result.response) {
              setTranscripts((prev) => [
                ...prev,
                { time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false }), speaker: 'HELIX', text: result.response },
              ])
            }

            if (result.audio) {
              setVoiceState('speaking')
              if (typeof window !== 'undefined' && (window as any).__helix_current_audio) {
                try {
                  (window as any).__helix_current_audio.pause()
                } catch {}
              }
              const audio = new Audio(`data:audio/wav;base64,${result.audio}`)
              currentAudioRef.current = audio
              if (typeof window !== 'undefined') {
                ;(window as any).__helix_current_audio = audio
              }
              audio.onended = () => {
                currentAudioRef.current = null
                if (typeof window !== 'undefined' && (window as any).__helix_current_audio === audio) {
                  ;(window as any).__helix_current_audio = null
                }
                setVoiceState('idle')
              }
              audio.play().catch(() => {
                currentAudioRef.current = null
                if (typeof window !== 'undefined' && (window as any).__helix_current_audio === audio) {
                  ;(window as any).__helix_current_audio = null
                }
                if (result.response) {
                  playVoiceFallback(result.response)
                } else {
                  setVoiceState('idle')
                }
              })
            } else if (result.response) {
              playVoiceFallback(result.response)
            } else {
              setVoiceState('idle')
            }
          } catch {
            setVoiceState('idle')
          }
        }

        recorder.start()
        setVoiceState('listening')
        setTranscript('')

        // VAD: Speech Activity & Silence detection
        try {
          const audioCtx = new (window.AudioContext || (window as any).webkitAudioContext)()
          audioContextRef.current = audioCtx
          const source = audioCtx.createMediaStreamSource(stream)
          const analyser = audioCtx.createAnalyser()
          analyser.fftSize = 512
          source.connect(analyser)

          const dataArray = new Float32Array(analyser.fftSize)
          let speechDetected = false
          let silenceStartTime: number | null = null
          const listenStartTime = Date.now()

          const checkVolume = () => {
            if (!mediaRecorder.current || mediaRecorder.current.state !== 'recording') return
            analyser.getFloatTimeDomainData(dataArray)
            let sumSquares = 0
            for (let i = 0; i < dataArray.length; i++) {
              sumSquares += dataArray[i] * dataArray[i]
            }
            const rms = Math.sqrt(sumSquares / dataArray.length)

            const now = Date.now()
            if (rms > 0.012) {
              speechDetected = true
              silenceStartTime = null
            } else {
              if (speechDetected) {
                if (!silenceStartTime) {
                  silenceStartTime = now
                } else if (now - silenceStartTime > 2200) {
                  // User finished speaking, detected 2.2s silence
                  stopAudioCapture()
                  if (mediaRecorder.current?.state === 'recording') {
                    setVoiceState('processing')
                    mediaRecorder.current.stop()
                  }
                  return
                }
              } else if (now - listenStartTime > 12000) {
                // No speech detected after 12 seconds
                stopAudioCapture()
                if (mediaRecorder.current?.state === 'recording') {
                  mediaRecorder.current.stop()
                }
                return
              }
            }

            animFrameRef.current = requestAnimationFrame(checkVolume)
          }

          animFrameRef.current = requestAnimationFrame(checkVolume)
        } catch {}

        maxTimeoutRef.current = setTimeout(() => {
          stopAudioCapture()
          if (mediaRecorder.current?.state === 'recording') {
            setVoiceState('processing')
            mediaRecorder.current.stop()
          }
        }, 35000)
      } catch {
        setVoiceState('idle')
      }
    }
  }, [voiceState, command, handleInterrupt, stopAudioCapture, activeSessionId])

  const cfg = stateConfig[voiceState]
  const Icon = cfg.icon

  return (
    <div className="flex h-full">
      {/* Main voice area */}
      <div className="flex-1 flex flex-col items-center justify-center gap-8 p-8">
        <motion.div
          key={voiceState}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn('flex items-center gap-2 text-sm font-mono', cfg.color)}
        >
          {Icon && <Icon className={cn("w-4 h-4", voiceState === 'processing' && "animate-spin")} />}
          {voiceState === 'listening' && (
            <motion.span className="w-2 h-2 rounded-full bg-[#00d4ff] animate-pulse-glow" />
          )}
          {cfg.label}
        </motion.div>

        {/* Central orb */}
        <div className="relative flex items-center justify-center">
          {[80, 60, 40].map((size, i) => (
            <motion.div
              key={i}
              className="absolute rounded-full border"
              style={{ width: 140 + size * 2, height: 140 + size * 2, borderColor: cfg.ringColor }}
              animate={voiceState !== 'idle' ? { scale: [1, 1.04, 1], opacity: [0.4, 0.15, 0.4] } : { scale: 1, opacity: 0.1 }}
              transition={{ duration: 2, repeat: Infinity, delay: i * 0.4 }}
            />
          ))}

          <motion.button
            onClick={toggle}
            whileHover={{ scale: 1.04 }}
            whileTap={{ scale: 0.96 }}
            className={cn(
              'relative w-36 h-36 rounded-full flex items-center justify-center transition-all',
              voiceState !== 'idle'
                ? 'bg-[rgba(0,212,255,0.15)] border-2 border-[#00d4ff] glow-cyan'
                : 'glass border border-[rgba(255,255,255,0.1)] hover:border-[rgba(0,212,255,0.3)]',
            )}
          >
            <AnimatePresence mode="wait">
              {voiceState === 'idle' ? (
                <motion.div key="idle" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}>
                  <Mic className="w-12 h-12 text-zinc-400" />
                </motion.div>
              ) : voiceState === 'listening' ? (
                <motion.div key="listen" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}>
                  <Mic className="w-12 h-12 text-[#00d4ff] drop-shadow-[0_0_12px_rgba(0,212,255,0.8)]" />
                </motion.div>
              ) : voiceState === 'processing' ? (
                <motion.div key="proc" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}>
                  <Zap className="w-12 h-12 text-[#7c3aed] drop-shadow-[0_0_12px_rgba(124,58,237,0.8)]" />
                </motion.div>
              ) : (
                <motion.div key="speak" initial={{ scale: 0.8, opacity: 0 }} animate={{ scale: 1, opacity: 1 }} exit={{ scale: 0.8, opacity: 0 }}>
                  <Volume2 className="w-12 h-12 text-[#22c55e] drop-shadow-[0_0_12px_rgba(34,197,94,0.8)]" />
                </motion.div>
              )}
            </AnimatePresence>
          </motion.button>
        </div>

        <WaveformVisualizer active={voiceState === 'listening' || voiceState === 'speaking'} />

        <AnimatePresence>
          {transcript && (
            <motion.div
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="max-w-md text-center"
            >
              <GlassCard className="text-sm text-zinc-300 italic leading-relaxed">
                &ldquo;{transcript}&rdquo;
              </GlassCard>
            </motion.div>
          )}
        </AnimatePresence>

        <div className="flex items-center gap-3">
          <button onClick={() => setMuted((v) => !v)} className="text-zinc-600 hover:text-zinc-300 transition-colors">
            {muted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
          </button>
          <input
            type="range" min={0} max={100} value={volume}
            onChange={(e) => setVolume(Number(e.target.value))}
            className="w-32 accent-[#00d4ff]"
          />
          <span className="text-xs font-mono text-zinc-600 w-8">{volume}%</span>
        </div>

        <p className="text-xs text-zinc-700 font-mono">
          {voiceState === 'idle' ? 'Click the microphone to begin' : 'Click again to stop'}
        </p>
      </div>

      {/* Right panel */}
      <div className="w-72 shrink-0 border-l border-[rgba(255,255,255,0.06)] flex flex-col">
        <div className="p-4 border-b border-[rgba(255,255,255,0.06)]">
          <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Voice Profile</h3>
          <div className="space-y-2">
            {voiceProfiles.map((p) => (
              <button
                key={p.name}
                className={cn(
                  'w-full flex items-center gap-3 p-2.5 rounded-lg transition-colors',
                  p.active ? 'bg-[rgba(0,212,255,0.08)] border border-[rgba(0,212,255,0.2)]' : 'hover:bg-[rgba(255,255,255,0.03)]',
                )}
              >
                <div className={cn('w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold font-mono', p.active ? 'bg-[rgba(0,212,255,0.15)] text-[#00d4ff]' : 'bg-[rgba(255,255,255,0.05)] text-zinc-600')}>
                  {p.name[0]}
                </div>
                <div className="text-left">
                  <div className={cn('text-sm font-medium', p.active ? 'text-zinc-200' : 'text-zinc-500')}>{p.name}</div>
                  <div className="text-[10px] text-zinc-700">{p.desc}</div>
                </div>
                {p.active && <div className="ml-auto w-1.5 h-1.5 rounded-full bg-[#00d4ff] animate-pulse-glow" />}
              </button>
            ))}
          </div>
        </div>

        <div className="flex-1 p-4 overflow-y-auto">
          <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Session Log</h3>
          <div className="space-y-3">
            {transcripts.length === 0 && (
              <p className="text-xs text-zinc-700">No voice interactions yet</p>
            )}
            {transcripts.map((t, i) => (
              <div key={i} className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <span className={cn('text-[10px] font-mono', t.speaker === 'HELIX' ? 'text-[#00d4ff]' : 'text-zinc-500')}>{t.speaker}</span>
                  <span className="text-[10px] text-zinc-700 font-mono">{t.time}</span>
                </div>
                <p className="text-xs text-zinc-400 leading-relaxed">{t.text}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="p-4 border-t border-[rgba(255,255,255,0.06)]">
          <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Shortcuts</h3>
          <div className="space-y-2">
            {shortcuts.map((s) => (
              <div key={s.key} className="flex items-center justify-between">
                <span className="text-xs text-zinc-600">{s.label}</span>
                <kbd className="text-[10px] font-mono bg-[rgba(255,255,255,0.05)] text-zinc-500 px-1.5 py-0.5 rounded border border-[rgba(255,255,255,0.08)]">{s.key}</kbd>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
