'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { useAggregatedContext } from '@/lib/hooks/use-context'
import { ChevronLeft, ChevronRight, RotateCcw, Lock, Plus, X, Globe, Star, Zap, Search } from 'lucide-react'
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

export function BrowserPage() {
  const { data: contextData } = useAggregatedContext()
  const browserObj = contextData?.context?.browser as { tabs?: Array<{ title: string; browser?: string }> } | undefined
  const browserTabs = browserObj?.tabs

  const initialTabs: Tab[] = browserTabs && browserTabs.length > 0
    ? browserTabs.map((t, i) => ({
        id: i.toString(),
        title: t.title ?? 'Browser Tab',
        url: '',
        favicon: '🌐',
        active: i === 0,
      }))
    : defaultTabs

  const [tabs, setTabs] = useState<Tab[]>(initialTabs)
  const [urlInput, setUrlInput] = useState(tabs.find((t) => t.active)?.url ?? '')
  const [showNewTab, setShowNewTab] = useState(false)

  const activeTab = tabs.find((t) => t.active) ?? tabs[0]

  const switchTab = (id: string) => {
    setTabs((prev) => prev.map((t) => ({ ...t, active: t.id === id })))
    const tab = tabs.find((t) => t.id === id)
    if (tab) setUrlInput(tab.url)
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
    setUrlInput('')
    setShowNewTab(true)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Tab bar */}
      <div className="flex items-center gap-0 border-b border-[rgba(255,255,255,0.06)] bg-[#0f0f11] shrink-0 overflow-x-auto">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            className={cn(
              'flex items-center gap-2 px-4 py-2.5 border-r border-[rgba(255,255,255,0.04)] min-w-0 max-w-[180px] group shrink-0 transition-colors',
              tab.active ? 'bg-[#09090b] text-zinc-300 border-b border-[#00d4ff]' : 'text-zinc-600 hover:bg-[rgba(255,255,255,0.03)] hover:text-zinc-400',
            )}
          >
            <span className="text-xs shrink-0">{tab.favicon}</span>
            <span className="text-xs truncate flex-1">{tab.title}</span>
            <button onClick={(e) => closeTab(tab.id, e)} className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:text-zinc-200 transition-all shrink-0">
              <X className="w-3 h-3" />
            </button>
          </button>
        ))}
        <button onClick={addTab} className="px-3 py-2.5 text-zinc-600 hover:text-zinc-300 transition-colors shrink-0">
          <Plus className="w-4 h-4" />
        </button>
      </div>

      {/* Nav bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-[rgba(255,255,255,0.06)] shrink-0">
        {[ChevronLeft, ChevronRight, RotateCcw].map((Icon, i) => (
          <button key={i} className="p-1.5 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-[rgba(255,255,255,0.04)] transition-colors">
            <Icon className="w-4 h-4" />
          </button>
        ))}

        <div className="flex-1 flex items-center gap-2 px-3 py-1.5 rounded-xl bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.07)] hover:border-[rgba(0,212,255,0.2)] focus-within:border-[rgba(0,212,255,0.3)] transition-colors">
          <Lock className="w-3 h-3 text-[#22c55e] shrink-0" />
          <input
            value={urlInput}
            onChange={(e) => setUrlInput(e.target.value)}
            className="flex-1 bg-transparent text-xs text-zinc-300 outline-none"
          />
          <Search className="w-3 h-3 text-zinc-700 shrink-0" />
        </div>

        <div className="hidden lg:flex items-center gap-1">
          {bookmarks.map((b) => (
            <button key={b.label} className="flex items-center gap-1 px-2 py-1 rounded-lg text-zinc-600 hover:text-zinc-300 hover:bg-[rgba(255,255,255,0.04)] transition-colors text-xs">
              <span>{b.icon}</span>
              <span className="hidden xl:inline text-[10px]">{b.label}</span>
            </button>
          ))}
        </div>

        <button className="p-1.5 rounded-lg text-zinc-600 hover:text-[#f59e0b] transition-colors">
          <Star className="w-4 h-4" />
        </button>
      </div>

      {/* Content area */}
      <div className="flex-1 overflow-auto">
        {activeTab.url === '' || showNewTab ? (
          <div className="p-8 max-w-3xl mx-auto space-y-8">
            <div className="text-center space-y-2">
              <Globe className="w-10 h-10 text-[#00d4ff] mx-auto animate-float" />
              <h2 className="text-xl font-bold text-zinc-200">HELIX Browser</h2>
              <p className="text-sm text-zinc-600">AI-enhanced browsing with memory integration</p>
            </div>

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
                    onClick={() => { setUrlInput(link.url); setShowNewTab(false) }}
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
          <div className="flex flex-col items-center justify-center h-full gap-6 p-8">
            <div className="w-16 h-16 rounded-2xl glass flex items-center justify-center text-3xl animate-float">
              {activeTab.favicon}
            </div>
            <div className="text-center">
              <h3 className="text-lg font-semibold text-zinc-200">{activeTab.title}</h3>
              <p className="text-sm text-zinc-600 mt-1 font-mono">{activeTab.url}</p>
            </div>
            <GlassCard className="max-w-md text-center">
              <div className="flex items-center gap-2 text-[#00d4ff] mb-2 justify-center">
                <Zap className="w-4 h-4" />
                <span className="text-sm font-medium">HELIX AI Integration Active</span>
              </div>
              <p className="text-xs text-zinc-500 leading-relaxed">
                Live browsing requires an external window. HELIX can summarize, analyze, and extract data from any page you visit using its AI layer.
              </p>
            </GlassCard>
          </div>
        )}
      </div>
    </div>
  )
}
