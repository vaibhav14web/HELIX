'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { useAggregatedContext } from '@/lib/hooks/use-context'
import { Folder, FileText, FileCode, Image, Archive, Music, Download, Trash2, Eye, Search, Grid3X3, List, ChevronRight, HardDrive, Plus } from 'lucide-react'
import { GlassCard } from '@/components/os/GlassCard'
import { cn } from '@/lib/utils'

interface FileItem {
  id: string
  name: string
  type: 'folder' | 'document' | 'code' | 'image' | 'archive' | 'audio'
  size?: string
  modified: string
  path: string
  items?: number
}

const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  folder: Folder,
  document: FileText,
  code: FileCode,
  image: Image,
  archive: Archive,
  audio: Music,
}

const colorMap: Record<string, string> = {
  folder: 'text-[#f59e0b]',
  document: 'text-[#00d4ff]',
  code: 'text-[#7c3aed]',
  image: 'text-[#22c55e]',
  archive: 'text-zinc-400',
  audio: 'text-[#ef4444]',
}

const defaultFiles: FileItem[] = [
  { id: '1', name: 'HELIX Core', type: 'folder', modified: 'Today', path: '/', items: 14 },
  { id: '2', name: 'Research Reports', type: 'folder', modified: 'Today', path: '/', items: 42 },
  { id: '3', name: 'Memory Exports', type: 'folder', modified: 'Yesterday', path: '/', items: 8 },
  { id: '4', name: 'Agent Configs', type: 'folder', modified: '2 days ago', path: '/', items: 6 },
  { id: '5', name: 'AI Infrastructure Analysis.pdf', type: 'document', size: '4.2 MB', modified: 'Today', path: '/' },
  { id: '6', name: 'market_research_q3.pdf', type: 'document', size: '2.8 MB', modified: 'Today', path: '/' },
  { id: '7', name: 'helix-core-v2.4.tar.gz', type: 'archive', size: '128 MB', modified: 'Yesterday', path: '/' },
  { id: '8', name: 'agent-runtime.ts', type: 'code', size: '18 KB', modified: '2 days ago', path: '/' },
  { id: '9', name: 'memory-graph-schema.json', type: 'code', size: '4 KB', modified: '3 days ago', path: '/' },
  { id: '10', name: 'system-screenshot-2026.png', type: 'image', size: '1.4 MB', modified: 'Last week', path: '/' },
  { id: '11', name: 'voice-session-2026-06-27.mp3', type: 'audio', size: '8.2 MB', modified: 'Today', path: '/' },
  { id: '12', name: 'automation-flows.json', type: 'code', size: '22 KB', modified: 'Today', path: '/' },
]

const breadcrumbs = ['HELIX Files', 'Home']

const storageItems = [
  { label: 'Documents', value: 14.2, total: 50, color: '#00d4ff' },
  { label: 'Code', value: 8.7, total: 50, color: '#7c3aed' },
  { label: 'Media', value: 22.1, total: 50, color: '#22c55e' },
  { label: 'Archives', value: 5.4, total: 50, color: '#f59e0b' },
]

export function FilesPage() {
  const { data: contextData } = useAggregatedContext()
  const [view, setView] = useState<'grid' | 'list'>('list')
  const [selected, setSelected] = useState<string[]>([])
  const [search, setSearch] = useState('')

  const recentFiles = contextData?.context?.recent_files as { files?: Array<{ path: string; modified: number; size_bytes: number; extension: string }> } | undefined
  const contextFiles = recentFiles?.files
  const files: FileItem[] = contextFiles && contextFiles.length > 0
    ? contextFiles.map((f, i) => {
        const name = f.path.split('\\').pop()?.split('/').pop() ?? f.path
        return {
          id: i.toString(),
          name,
          type: f.extension === '.pdf' || f.extension === '.docx' ? 'document'
            : f.extension === '.ts' || f.extension === '.py' || f.extension === '.json' ? 'code'
            : f.extension === '.png' || f.extension === '.jpg' || f.extension === '.jpeg' ? 'image'
            : f.extension === '.zip' || f.extension === '.tar.gz' || f.extension === '.gz' ? 'archive'
            : f.extension === '.mp3' || f.extension === '.wav' ? 'audio'
            : 'document',
          size: f.size_bytes ? `${(f.size_bytes / 1024 / 1024).toFixed(1)} MB` : undefined,
          modified: f.modified ? new Date(f.modified * 1000).toLocaleDateString() : 'Unknown',
          path: f.path,
        }
      })
    : defaultFiles

  const filtered = files.filter((f) => f.name.toLowerCase().includes(search.toLowerCase()))
  const toggle = (id: string) => setSelected((s) => s.includes(id) ? s.filter((x) => x !== id) : [...s, id])

  return (
    <div className="flex h-full">
      <div className="w-56 shrink-0 border-r border-[rgba(255,255,255,0.06)] flex flex-col">
        <div className="p-4 border-b border-[rgba(255,255,255,0.06)]">
          <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Storage</h3>
          <GlassCard className="space-y-3">
            <div className="flex items-center gap-2">
              <HardDrive className="w-4 h-4 text-[#00d4ff]" />
              <div>
                <div className="text-sm font-bold font-mono text-zinc-200">2.4 TB</div>
                <div className="text-[10px] text-zinc-600">of 8 TB used</div>
              </div>
            </div>
            <div className="w-full h-1.5 bg-[rgba(255,255,255,0.06)] rounded-full overflow-hidden flex">
              {storageItems.map((s) => (
                <div key={s.label} className="h-full rounded-none" style={{ width: `${(s.value / 50) * 100}%`, background: s.color }} />
              ))}
            </div>
            {storageItems.map((s) => (
              <div key={s.label} className="flex items-center justify-between">
                <div className="flex items-center gap-1.5">
                  <div className="w-1.5 h-1.5 rounded-full" style={{ background: s.color }} />
                  <span className="text-xs text-zinc-500">{s.label}</span>
                </div>
                <span className="text-xs font-mono text-zinc-600">{s.value} GB</span>
              </div>
            ))}
          </GlassCard>
        </div>
        <div className="p-3 flex-1">
          <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-2">Quick Access</h3>
          {['Documents', 'Downloads', 'Research', 'Code', 'Agents'].map((label) => (
            <button key={label} className="w-full flex items-center gap-2 px-2 py-2 rounded-lg text-left text-xs text-zinc-500 hover:text-zinc-200 hover:bg-[rgba(255,255,255,0.03)] transition-colors">
              <Folder className="w-3.5 h-3.5 text-[#f59e0b]" />
              {label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex-1 flex flex-col min-w-0">
        <div className="flex items-center gap-3 px-4 py-3 border-b border-[rgba(255,255,255,0.06)] shrink-0">
          <div className="flex items-center gap-1 text-xs text-zinc-500">
            {breadcrumbs.map((crumb, i) => (
              <span key={crumb} className="flex items-center gap-1">
                {i > 0 && <ChevronRight className="w-3 h-3 text-zinc-700" />}
                <span className={cn(i === breadcrumbs.length - 1 ? 'text-zinc-300' : 'hover:text-zinc-300 cursor-pointer')}>{crumb}</span>
              </span>
            ))}
          </div>
          <div className="flex-1" />
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search files..."
              className="pl-8 pr-3 py-1.5 bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.07)] rounded-lg text-xs text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-[rgba(0,212,255,0.3)] w-40 transition-colors"
            />
          </div>
          <div className="flex items-center gap-1 bg-[rgba(255,255,255,0.04)] rounded-lg p-1">
            {([['list', List], ['grid', Grid3X3]] as const).map(([v, Icon]) => (
              <button key={v} onClick={() => setView(v)} className={cn('p-1.5 rounded transition-colors', view === v ? 'bg-[rgba(0,212,255,0.1)] text-[#00d4ff]' : 'text-zinc-600 hover:text-zinc-300')}>
                <Icon className="w-3.5 h-3.5" />
              </button>
            ))}
          </div>
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[rgba(0,212,255,0.08)] border border-[rgba(0,212,255,0.2)] text-[#00d4ff] text-xs font-medium hover:bg-[rgba(0,212,255,0.12)] transition-colors">
            <Plus className="w-3.5 h-3.5" /> Upload
          </button>
        </div>

        {selected.length > 0 && (
          <motion.div initial={{ opacity: 0, y: -4 }} animate={{ opacity: 1, y: 0 }} className="flex items-center gap-3 px-4 py-2 bg-[rgba(0,212,255,0.05)] border-b border-[rgba(0,212,255,0.1)]">
            <span className="text-xs text-zinc-400">{selected.length} selected</span>
            {[{ Icon: Download, label: 'Download' }, { Icon: Trash2, label: 'Delete' }].map(({ Icon, label }) => (
              <button key={label} className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs text-zinc-400 hover:text-zinc-200 hover:bg-[rgba(255,255,255,0.05)] transition-colors">
                <Icon className="w-3.5 h-3.5" /> {label}
              </button>
            ))}
          </motion.div>
        )}

        <div className="flex-1 overflow-y-auto p-4">
          {view === 'list' ? (
            <div className="space-y-1">
              <div className="grid grid-cols-[auto,1fr,80px,100px,80px] gap-4 px-3 py-1.5 text-[10px] font-mono uppercase tracking-wider text-zinc-700">
                <span className="w-4" />
                <span>Name</span>
                <span className="text-right">Size</span>
                <span>Modified</span>
                <span />
              </div>
              {filtered.map((file, i) => {
                const Icon = iconMap[file.type]
                const color = colorMap[file.type]
                const isSelected = selected.includes(file.id)
                return (
                  <motion.div
                    key={file.id}
                    initial={{ opacity: 0, x: -4 }}
                    animate={{ opacity: 1, x: 0 }}
                    transition={{ delay: i * 0.03 }}
                    onClick={() => toggle(file.id)}
                    className={cn(
                      'grid grid-cols-[auto,1fr,80px,100px,80px] gap-4 items-center px-3 py-2.5 rounded-lg cursor-pointer transition-colors group',
                      isSelected ? 'bg-[rgba(0,212,255,0.07)]' : 'hover:bg-[rgba(255,255,255,0.03)]',
                    )}
                  >
                    <input type="checkbox" checked={isSelected} onChange={() => toggle(file.id)} onClick={(e) => e.stopPropagation()} className="w-3.5 h-3.5 accent-[#00d4ff]" />
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Icon className={cn('w-4 h-4 shrink-0', color)} />
                      <span className="text-sm text-zinc-300 truncate">{file.name}</span>
                      {file.items && <span className="text-[10px] text-zinc-700 shrink-0">{file.items} items</span>}
                    </div>
                    <div className="text-xs text-zinc-600 font-mono text-right">{file.size ?? '—'}</div>
                    <div className="text-xs text-zinc-600 font-mono">{file.modified}</div>
                    <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                      <button onClick={(e) => { e.stopPropagation() }} className="p-1 rounded hover:text-zinc-200 text-zinc-600 transition-colors"><Eye className="w-3.5 h-3.5" /></button>
                      <button onClick={(e) => { e.stopPropagation() }} className="p-1 rounded hover:text-zinc-200 text-zinc-600 transition-colors"><Download className="w-3.5 h-3.5" /></button>
                    </div>
                  </motion.div>
                )
              })}
            </div>
          ) : (
            <div className="grid grid-cols-3 md:grid-cols-4 lg:grid-cols-6 gap-3">
              {filtered.map((file, i) => {
                const Icon = iconMap[file.type]
                const color = colorMap[file.type]
                const isSelected = selected.includes(file.id)
                return (
                  <motion.div
                    key={file.id}
                    initial={{ opacity: 0, scale: 0.95 }}
                    animate={{ opacity: 1, scale: 1 }}
                    transition={{ delay: i * 0.03 }}
                    onClick={() => toggle(file.id)}
                    className={cn(
                      'flex flex-col items-center gap-2 p-4 rounded-xl cursor-pointer transition-colors text-center',
                      isSelected ? 'bg-[rgba(0,212,255,0.07)] border border-[rgba(0,212,255,0.2)]' : 'glass hover:border-[rgba(255,255,255,0.12)]',
                    )}
                  >
                    <Icon className={cn('w-8 h-8', color)} />
                    <span className="text-xs text-zinc-400 truncate w-full">{file.name}</span>
                    <span className="text-[10px] text-zinc-700 font-mono">{file.size ?? (file.items ? `${file.items} items` : '—')}</span>
                  </motion.div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
