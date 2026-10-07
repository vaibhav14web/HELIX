'use client'

import { useEffect, useMemo, useState } from 'react'
import { motion } from 'framer-motion'
import { useAggregatedContext } from '@/lib/hooks/use-context'
import { ChevronLeft, ChevronRight, RotateCcw, Lock, Plus, X, Globe, Star, Zap, Search, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'
import { GlassCard } from '@/components/os/GlassCard'

interface Tab {
  id: string
  title: string
  url: string
  favicon: string
  active: boolean
}

const defaultTabs: Tab[] = [
  { id: '1', title: 'New Tab', url: '', favicon: '🌐', active: true },
]

const aiSuggestions = [
  'Summarize the top AI papers from today',
  'Find recent research on autonomous agents',
  'Compare GPT-5 vs Claude 4 benchmarks',
  'What\'s trending on Hacker News?',
]

const bookmarks = [
  { label: 'GitHub', icon: '💻', url: 'https://github.com' },
  { label: 'Docs', icon: '📄', url: 'https://opencode.ai/docs' },
  { label: 'AI Hub', icon: '🤖', url: 'https://huggingface.co' },
  { label: 'Analytics', icon: '📊', url: 'https://analytics.google.com' },
]

const quickLinks = [
  { label: 'HELIX Home', icon: '🏠', url: 'https://helix.ai', color: 'text-zinc-300', desc: 'AI platform dashboard' },
  { label: 'Research', icon: '🔬', url: 'https://scholar.google.com', color: 'text-zinc-300', desc: 'Academic search' },
  { label: 'Models', icon: '🧠', url: 'https://huggingface.co/models', color: 'text-zinc-300', desc: 'Model hub' },
  { label: 'Code', icon: '📝', url: 'https://github.com', color: 'text-zinc-300', desc: 'Source control' },
  { label: 'News', icon: '📰', url: 'https://news.ycombinator.com', color: 'text-zinc-300', desc: 'Tech news' },
  { label: 'MCP', icon: '🔌', url: 'https://opencode.ai/mcp', color: 'text-zinc-300', desc: 'Plugin registry' },
  { label: 'Alerts', icon: '🔔', url: 'https://status.helix.ai', color: 'text-zinc-300', desc: 'System status' },
  { label: 'Chat', icon: '💬', url: 'https://chat.helix.ai', color: 'text-zinc-300', desc: 'AI assistant' },
]

function normalizeUrl(raw: string) {
  const trimmed = raw.trim()
  if (!trimmed) return ''
  if (/^https?:\/\//i.test(trimmed)) return trimmed
  return `https://${trimmed}`
}

export function BrowserPage() {
  const { data: contextData } = useAggregatedContext()
  const browserObj = contextData?.context?.browser as { tabs?: Array<{ title: string; browser?: string }> } | undefined
  const browserTabs = browserObj?.tabs

  const initialTabs: Tab[] = useMemo(() => {
    return browserTabs && browserTabs.length > 0
      ? browserTabs.map((t, i) => ({
          id: i.toString(),
          title: t.title ?? 'Browser Tab',
          url: '',
          favicon: '🌐',
          active: i === 0,
        }))
      : defaultTabs
  }, [browserTabs])

  const [tabs, setTabs] = useState<Tab[]>(initialTabs)
  const [urlInput, setUrlInput] = useState('https://example.com')
  const [activeUrl, setActiveUrl] = useState('')
  const [error, setError] = useState('')
  const [showNewTab, setShowNewTab] = useState(true)

  useEffect(() => {
    setTabs(initialTabs)
    setUrlInput(initialTabs.find((tab) => tab.active)?.url ?? 'https://example.com')
    setActiveUrl('')
  }, [initialTabs])

  const activeTab = tabs.find((t) => t.active) ?? tabs[0]

  const switchTab = (id: string) => {
    setTabs((prev) => prev.map((t) => ({ ...t, active: t.id === id })))
    const tab = tabs.find((t) => t.id === id)
    if (tab) {
      setUrlInput(tab.url || 'https://example.com')
      setActiveUrl(tab.url || '')
      setShowNewTab(!tab.url)
    }
  }

  const closeTab = (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    setTabs((prev) => {
      const remaining = prev.filter((t) => t.id !== id)
      if (remaining.length === 0) return prev
      if (prev.find((t) => t.id === id)?.active) remaining[0].active = true
      return remaining
    })
  }

  const addTab = () => {
    const id = Date.now().toString()
    setTabs((prev) => [
      ...prev.map((t) => ({ ...t, active: false })),
      { id, title: 'New Tab', url: '', favicon: '🌐', active: true },
    ])
    setUrlInput('https://example.com')
    setActiveUrl('')
    setShowNewTab(true)
    setError('')
  }

  const goToUrl = (value?: string) => {
    const nextUrl = normalizeUrl(value ?? urlInput)
    if (!nextUrl) {
      setError('Enter a URL to open')
      return
    }
    try {
      new URL(nextUrl)
    } catch {
      setError('Please enter a valid page URL')
      return
    }
    setError('')
    setUrlInput(nextUrl)
    setActiveUrl(nextUrl)
    setShowNewTab(false)
    setTabs((prev) => prev.map((tab) => (tab.active ? { ...tab, title: new URL(nextUrl).hostname, url: nextUrl } : tab)))
  }

  const openNative = async (urlToOpen: string) => {
    try {
      const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
      await fetch(`${API_BASE}/browser/open`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: urlToOpen }),
      })
    } catch {
      window.open(urlToOpen, '_blank', 'noreferrer')
    }
  }

  const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  const iframeSrc = activeUrl ? `${API_BASE}/browser/proxy?url=${encodeURIComponent(activeUrl)}` : ''

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-0 border-b border-[rgba(255,255,255,0.06)] bg-[#0f0f11] shrink-0 overflow-x-auto">
        {tabs.map((tab) => (
          <div
            key={tab.id}
            role="button"
            tabIndex={0}
            onClick={() => switchTab(tab.id)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault()
                switchTab(tab.id)
              }
            }}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 border-r border-[rgba(255,255,255,0.04)] min-w-0 max-w-[180px] group shrink-0 transition-colors cursor-pointer select-none',
              tab.active ? 'bg-[#09090b] text-zinc-300 border-b border-[#00d4ff]' : 'text-zinc-600 hover:bg-[rgba(255,255,255,0.03)] hover:text-zinc-400',
            )}
          >
            <span className="text-xs shrink-0">{tab.favicon}</span>
            <span className="text-xs truncate flex-1">{tab.title}</span>
            <button
              type="button"
              onClick={(e) => closeTab(tab.id, e)}
              className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-zinc-200 transition-all shrink-0"
            >
              <X className="w-3 h-3" />
            </button>
          </div>
        ))}
        <button onClick={addTab} className="px-3 py-2.5 text-zinc-600 hover:text-zinc-300 transition-colors shrink-0">
          <Plus className="w-4 h-4" />
        </button>
      </div>

      <div className="flex items-center gap-2 px-3 py-2 border-b border-[rgba(255,255,255,0.06)] shrink-0">
        {[ChevronLeft, ChevronRight, RotateCcw].map((Icon, i) => (
          <button key={i} onClick={() => goToUrl(activeUrl || urlInput)} className="p-1.5 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-[rgba(255,255,255,0.04)] transition-colors">
            <Icon className="w-4 h-4" />
          </button>
        ))}

        <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.07)] hover:border-[rgba(0,212,255,0.2)] focus-within:border-[rgba(0,212,255,0.3)] transition-colors">
          <Lock className="w-3 h-3 text-[#22c55e] shrink-0" />
          <input
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            onKeyDown={(event) => event.key === 'Enter' && goToUrl()}
            className="flex-1 bg-transparent text-xs text-zinc-300 outline-none"
          />
          <button onClick={() => goToUrl()} className="rounded bg-[rgba(0,212,255,0.12)] px-2 py-1 text-[10px] font-medium text-[#00d4ff]">Go</button>
        </div>

        <div className="hidden lg:flex items-center gap-1">
          {bookmarks.map((b) => (
            <button key={b.label} onClick={() => goToUrl(b.url)} className="flex items-center gap-1 px-2 py-1 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-[rgba(255,255,255,0.04)] transition-colors text-xs">
              <span>{b.icon}</span>
              <span className="hidden xl:inline text-[10px]">{b.label}</span>
            </button>
          ))}
        </div>

        <button className="p-1.5 rounded-lg text-zinc-600 hover:text-[#f59e0b] transition-colors">
          <Star className="w-4 h-4" />
        </button>
      </div>

      <div className="flex-1 overflow-auto">
        {showNewTab || !activeUrl ? (
          <div className="p-8 max-w-3xl mx-auto space-y-8">
            <div className="text-center space-y-2">
              <Globe className="w-10 h-10 text-[#00d4ff] mx-auto animate-float" />
              <h2 className="text-xl font-bold text-zinc-200">HELIX Browser</h2>
              <p className="text-sm text-zinc-600">AI-enhanced browsing with memory integration</p>
            </div>

            {error ? <div className="rounded-xl border border-[rgba(239,68,68,0.2)] bg-[rgba(239,68,68,0.08)] px-3 py-2 text-sm text-red-300">{error}</div> : null}

            {browserTabs && browserTabs.length > 0 && (
              <div>
                <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-4">
                  <Zap className="inline w-3 h-3 mr-1" /> Live Browser Tabs
                </h3>
                <div className="space-y-2">
                  {browserTabs.map((t, i) => (
                    <div key={i} className="glass rounded-xl p-3 flex items-center gap-3">
                      <Globe className="w-4 h-4 text-[#00d4ff] shrink-0" />
                      <div className="min-w-0">
                        <div className="text-sm text-zinc-300 truncate">{t.title}</div>
                        <div className="text-[10px] text-zinc-600 font-mono truncate">Live browser tab</div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div>
              <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-4">Quick Links</h3>
              <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
                {quickLinks.map((link) => (
                  <button
                    key={link.url}
                    onClick={() => goToUrl(link.url)}
                    className="glass rounded-xl p-4 flex items-start gap-3 text-left hover:border-[rgba(0,212,255,0.15)] transition-colors group"
                  >
                    <span className="text-2xl">{link.icon}</span>
                    <div>
                      <div className={cn('text-sm font-medium', link.color)}>{link.label}</div>
                      <div className="text-[10px] text-zinc-600 mt-0.5">{link.desc}</div>
                    </div>
                  </button>
                ))}
              </div>
            </div>

            <div>
              <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-4">
                <Zap className="inline w-3 h-3 mr-1" /> AI Browse Suggestions
              </h3>
              <div className="space-y-2">
                {aiSuggestions.map((s) => (
                  <button key={s} className="w-full flex items-center gap-3 px-4 py-3 rounded-xl glass text-left hover:border-[rgba(0,212,255,0.15)] transition-colors group">
                    <Search className="w-4 h-4 text-zinc-600 shrink-0" />
                    <span className="text-sm text-zinc-400 group-hover:text-zinc-200 transition-colors">{s}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex flex-col h-full">
            <div className="flex items-center justify-between border-b border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] px-4 py-2.5 text-xs text-zinc-500">
              <span className="font-mono text-zinc-300 truncate max-w-md">{activeTab.title}</span>
              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => openNative(activeUrl)}
                  className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-[rgba(0,212,255,0.1)] border border-[rgba(0,212,255,0.25)] text-xs text-[#00d4ff] hover:bg-[rgba(0,212,255,0.2)] transition-colors"
                >
                  <Globe className="w-3.5 h-3.5" />
                  Open in Desktop Browser
                </button>
                <a href={activeUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-zinc-400 hover:text-zinc-200">
                  External tab <ExternalLink className="w-3.5 h-3.5" />
                </a>
              </div>
            </div>
            <div className="flex-1 bg-[#09090b] p-2">
              <iframe
                src={iframeSrc}
                title={activeTab.title}
                sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
                className="h-full w-full rounded-xl border border-[rgba(255,255,255,0.08)] bg-white"
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
