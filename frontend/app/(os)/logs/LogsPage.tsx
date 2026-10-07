'use client'

import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import { motion } from 'framer-motion'
import { Terminal, Search, Clock, AlertCircle, Info, AlertTriangle, Bug, Copy, RefreshCw } from 'lucide-react'
import { cn } from '@/lib/utils'

type LogLevel = 'info' | 'warn' | 'error' | 'debug'
type LogCategory = 'all' | 'system' | 'voice' | 'automation' | 'permissions'

const levelConfig: Record<LogLevel, { icon: React.ComponentType<{ className?: string }>; color: string; bg: string }> = {
  info: { icon: Info, color: 'text-[#00d4ff]', bg: 'bg-[rgba(0,212,255,0.08)]' },
  warn: { icon: AlertTriangle, color: 'text-[#f59e0b]', bg: 'bg-[rgba(245,158,11,0.08)]' },
  error: { icon: AlertCircle, color: 'text-[#ef4444]', bg: 'bg-[rgba(239,68,68,0.08)]' },
  debug: { icon: Bug, color: 'text-[#7c3aed]', bg: 'bg-[rgba(124,58,237,0.08)]' },
}

export function LogsPage() {
  const [search, setSearch] = useState('')
  const [levelFilter, setLevelFilter] = useState<LogLevel | 'all'>('all')
  const [categoryFilter, setCategoryFilter] = useState<LogCategory>('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [copyState, setCopyState] = useState('Copy')

  const { data: logsData, refetch, isFetching } = useQuery({
    queryKey: ['system_logs', levelFilter],
    queryFn: () => {
      const level = levelFilter === 'all'
        ? undefined
        : levelFilter === 'warn'
        ? 'WARNING'
        : levelFilter.toUpperCase()
      return api.system.logs(level, 150)
    },
    refetchInterval: 3000,
  })

  const logs = logsData?.logs || []

  const filtered = logs.filter((l) => {
    if (categoryFilter !== 'all') {
      const mod = l.module.toLowerCase()
      const isVoice = mod.includes('voice') || mod.includes('wake')
      const isAutomation = mod.includes('automation') || mod.includes('plan') || mod.includes('action') || mod.includes('productivity')
      const isPermissions = mod.includes('permission')

      if (categoryFilter === 'voice' && !isVoice) return false
      if (categoryFilter === 'automation' && !isAutomation) return false
      if (categoryFilter === 'permissions' && !isPermissions) return false
      if (categoryFilter === 'system' && (isVoice || isAutomation || isPermissions)) return false
    }

    if (search) {
      const s = search.toLowerCase()
      if (!l.message.toLowerCase().includes(s) && !l.module.toLowerCase().includes(s)) {
        return false
      }
    }

    return true
  })

  const copyLogs = async () => {
    const text = filtered.map((log) => `[${log.level}] ${log.module}: ${log.message}`).join('\n')
    try {
      await navigator.clipboard.writeText(text)
      setCopyState('Copied')
      setTimeout(() => setCopyState('Copy'), 1200)
    } catch {
      setCopyState('Failed')
      setTimeout(() => setCopyState('Copy'), 1200)
    }
  }

  return (
    <div className="flex flex-col h-full bg-[#09090b]">
      <div className="flex flex-wrap items-center gap-3 px-6 py-4 border-b border-[rgba(255,255,255,0.06)] shrink-0">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-[#00d4ff]" />
          <h1 className="text-sm font-semibold text-zinc-200">System Logs</h1>
        </div>

        <div className="relative ml-2">
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search message/module..."
            className="pl-8 pr-3 py-1.5 bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.07)] rounded-lg text-xs text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-[rgba(0,212,255,0.3)] w-48 transition-colors"
          />
        </div>

        <div className="flex items-center gap-1 bg-[rgba(255,255,255,0.02)] p-0.5 rounded-lg border border-[rgba(255,255,255,0.04)]">
          {(['all', 'info', 'warn', 'error', 'debug'] as const).map((l) => (
            <button
              key={l}
              onClick={() => setLevelFilter(l)}
              className={cn(
                'px-2.5 py-1 rounded-md text-[11px] capitalize font-medium transition-all cursor-pointer',
                levelFilter === l
                  ? 'bg-[rgba(0,212,255,0.08)] text-[#00d4ff] border border-[rgba(0,212,255,0.15)] shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-300 border border-transparent',
              )}
            >
              {l}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-1 bg-[rgba(255,255,255,0.02)] p-0.5 rounded-lg border border-[rgba(255,255,255,0.04)]">
          {(['all', 'system', 'voice', 'automation', 'permissions'] as const).map((c) => (
            <button
              key={c}
              onClick={() => setCategoryFilter(c)}
              className={cn(
                'px-2.5 py-1 rounded-md text-[11px] capitalize font-medium transition-all cursor-pointer',
                categoryFilter === c
                  ? 'bg-[rgba(124,58,237,0.08)] text-[#a78bfa] border border-[rgba(124,58,237,0.15)] shadow-sm'
                  : 'text-zinc-500 hover:text-zinc-300 border border-transparent',
              )}
            >
              {c}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        <button onClick={() => refetch()} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-[rgba(255,255,255,0.06)] text-zinc-400 hover:text-zinc-200">
          <RefreshCw className={cn('w-3 h-3', isFetching && 'animate-spin')} />
          Refresh
        </button>

        <button onClick={copyLogs} className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border border-[rgba(0,212,255,0.15)] bg-[rgba(0,212,255,0.08)] text-[#00d4ff]">
          <Copy className="w-3 h-3" />
          {copyState}
        </button>

        <button
          onClick={() => setAutoScroll((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs border transition-all cursor-pointer',
            autoScroll
              ? 'bg-[rgba(0,212,255,0.08)] border-[rgba(0,212,255,0.2)] text-[#00d4ff]'
              : 'text-zinc-600 border-transparent hover:text-zinc-400'
          )}
        >
          <Clock className="w-3 h-3" />
          Auto-scroll
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] leading-relaxed bg-[#0c0c0e]">
        <div className="space-y-1">
          {filtered.length > 0 ? (
            filtered.map((log, index) => {
              const rawLvl = log.level.toLowerCase()
              const lvl: LogLevel = rawLvl === 'warning' ? 'warn' : rawLvl as LogLevel
              const cfg = levelConfig[lvl] || levelConfig.info
              const Icon = cfg.icon
              const logKey = `${log.timestamp}-${index}`

              return (
                <motion.div
                  key={logKey}
                  initial={{ opacity: 0, x: -4 }}
                  animate={{ opacity: 1, x: 0 }}
                  className="flex items-start gap-3 px-3 py-1.5 rounded-md hover:bg-[rgba(255,255,255,0.02)] transition-colors group"
                >
                  <span className={cn('text-zinc-700 w-16 shrink-0 font-mono transition-opacity', autoScroll && 'opacity-60')}>
                    {(() => {
                      if (!log.timestamp) return '--:--:--'
                      try {
                        const d = new Date(log.timestamp)
                        if (!isNaN(d.getTime())) {
                          return d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })
                        }
                      } catch {
                        // ignore fallback
                      }
                      const parts = log.timestamp.split('T')[1] || log.timestamp.split(' ')[1] || log.timestamp
                      return parts.split('.')[0].split(',')[0].slice(0, 8)
                    })()}
                  </span>
                  <div className={cn('p-0.5 rounded shrink-0', cfg.bg)}>
                    <Icon className={cn('w-3 h-3', cfg.color)} />
                  </div>
                  <span className={cn('text-zinc-500 w-24 shrink-0 font-semibold truncate', cfg.color)}>
                    {log.module}
                  </span>
                  <span className="text-zinc-300 select-text whitespace-pre-wrap break-all flex-1">{log.message}</span>
                </motion.div>
              )
            })
          ) : (
            <div className="flex items-center justify-center py-20 text-zinc-700 font-mono text-xs">
              No matching log records found.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
