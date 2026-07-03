'use client'

import { useCallback, useState } from 'react'
import ReactFlow, {
  Background,
  Controls,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Connection,
  type Node,
  BackgroundVariant,
} from 'reactflow'
import 'reactflow/dist/style.css'
import { GlassCard } from '@/components/os/GlassCard'
import { StatusBadge } from '@/components/os/GlassCard'
import { Search, GitBranch, Plus, Layers, Clock, TrendingUp } from 'lucide-react'
import { motion } from 'framer-motion'
import { cn } from '@/lib/utils'
import { useMemoryNodes } from '@/lib/hooks/use-memory'

type NodeCategory = 'concept' | 'person' | 'project' | 'event' | 'tool'

const categoryConfig: Record<NodeCategory, { color: string; border: string; bg: string }> = {
  concept: { color: '#00d4ff', border: 'rgba(0,212,255,0.4)', bg: 'rgba(0,212,255,0.1)' },
  person: { color: '#22c55e', border: 'rgba(34,197,94,0.4)', bg: 'rgba(34,197,94,0.1)' },
  project: { color: '#7c3aed', border: 'rgba(124,58,237,0.4)', bg: 'rgba(124,58,237,0.1)' },
  event: { color: '#f59e0b', border: 'rgba(245,158,11,0.4)', bg: 'rgba(245,158,11,0.1)' },
  tool: { color: '#ef4444', border: 'rgba(239,68,68,0.4)', bg: 'rgba(239,68,68,0.1)' },
}

function MemoryNode({ data }: { data: { label: string; category: NodeCategory; weight: number; connections: number } }) {
  const cfg = categoryConfig[data.category]
  return (
    <div
      className="px-3 py-2 rounded-xl text-xs font-medium transition-all"
      style={{
        background: cfg.bg,
        border: `1px solid ${cfg.border}`,
        color: cfg.color,
        minWidth: 100,
        boxShadow: `0 0 12px ${cfg.color}22`,
      }}
    >
      <div className="font-mono font-bold text-xs" style={{ color: cfg.color }}>{data.label}</div>
      <div className="text-[10px] mt-0.5 opacity-60">{data.connections} links</div>
    </div>
  )
}

const nodeTypes = { memory: MemoryNode }

const initialNodes: Node[] = [
  { id: '1', type: 'memory', position: { x: 400, y: 200 }, data: { label: 'HELIX PAIOS', category: 'project', weight: 10, connections: 8 } },
  { id: '2', type: 'memory', position: { x: 200, y: 100 }, data: { label: 'AI Infrastructure', category: 'concept', weight: 8, connections: 6 } },
  { id: '3', type: 'memory', position: { x: 600, y: 100 }, data: { label: 'Agent Runtime', category: 'tool', weight: 7, connections: 5 } },
  { id: '4', type: 'memory', position: { x: 150, y: 300 }, data: { label: 'ResearchBot', category: 'tool', weight: 6, connections: 4 } },
  { id: '5', type: 'memory', position: { x: 650, y: 300 }, data: { label: 'Memory Engine', category: 'tool', weight: 6, connections: 4 } },
  { id: '6', type: 'memory', position: { x: 300, y: 380 }, data: { label: 'Language Model', category: 'concept', weight: 9, connections: 7 } },
  { id: '7', type: 'memory', position: { x: 520, y: 380 }, data: { label: 'Vector DB', category: 'tool', weight: 5, connections: 3 } },
  { id: '8', type: 'memory', position: { x: 80, y: 180 }, data: { label: 'Dr. Sam Rivera', category: 'person', weight: 4, connections: 3 } },
  { id: '9', type: 'memory', position: { x: 750, y: 200 }, data: { label: 'Product Launch', category: 'event', weight: 5, connections: 3 } },
  { id: '10', type: 'memory', position: { x: 350, y: 500 }, data: { label: 'Transformer Arch.', category: 'concept', weight: 7, connections: 5 } },
  { id: '11', type: 'memory', position: { x: 480, y: 500 }, data: { label: 'Embeddings', category: 'concept', weight: 6, connections: 4 } },
  { id: '12', type: 'memory', position: { x: 200, y: 480 }, data: { label: 'Q3 Roadmap', category: 'project', weight: 5, connections: 3 } },
]

const initialEdges = [
  { id: 'e1-2', source: '1', target: '2', animated: true },
  { id: 'e1-3', source: '1', target: '3', animated: true },
  { id: 'e2-4', source: '2', target: '4' },
  { id: 'e3-5', source: '3', target: '5' },
  { id: 'e1-6', source: '1', target: '6', animated: true },
  { id: 'e6-7', source: '6', target: '7' },
  { id: 'e2-8', source: '2', target: '8' },
  { id: 'e1-9', source: '1', target: '9' },
  { id: 'e6-10', source: '6', target: '10', animated: true },
  { id: 'e7-11', source: '7', target: '11' },
  { id: 'e1-12', source: '1', target: '12' },
  { id: 'e4-6', source: '4', target: '6' },
  { id: 'e5-7', source: '5', target: '7' },
  { id: 'e10-11', source: '10', target: '11' },
]

const recentMemories: { text: string; time: string; category: NodeCategory }[] = []

const filterOptions = ['All', 'Concept', 'Person', 'Project', 'Event', 'Tool']

export function MemoryPage() {
  const { stats: systemStats } = useMemoryNodes()
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [activeFilter, setActiveFilter] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')

  const onConnect = useCallback(
    (params: Connection) => setEdges((eds) => addEdge({ ...params, animated: true }, eds)),
    [setEdges],
  )

  const stats = [
    { label: 'Conversations', value: String(systemStats?.data?.conversations ?? 0), icon: Layers, color: 'text-[#00d4ff]' },
    { label: 'Preferences', value: String(systemStats?.data?.preferences ?? 0), icon: GitBranch, color: 'text-[#7c3aed]' },
    { label: 'Explanations', value: String(systemStats?.data?.explanations ?? 0), icon: Clock, color: 'text-[#22c55e]' },
    { label: 'Permissions', value: String(systemStats?.data?.permissions_historical ?? 0), icon: TrendingUp, color: 'text-[#f59e0b]' },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Top bar */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-[rgba(255,255,255,0.06)] shrink-0">
        <div className="flex items-center gap-4">
          <div className="relative">
            <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-zinc-600" />
            <input
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search memory..."
              className="pl-8 pr-3 py-1.5 bg-[rgba(255,255,255,0.04)] border border-[rgba(255,255,255,0.07)] rounded-lg text-xs text-zinc-300 placeholder:text-zinc-600 outline-none focus:border-[rgba(0,212,255,0.3)] w-48 transition-colors"
            />
          </div>
          <div className="flex items-center gap-1">
            {filterOptions.map((f) => (
              <button
                key={f}
                onClick={() => setActiveFilter(f)}
                className={cn(
                  'px-2.5 py-1 rounded-lg text-xs font-medium transition-colors',
                  activeFilter === f ? 'bg-[rgba(0,212,255,0.1)] text-[#00d4ff]' : 'text-zinc-600 hover:text-zinc-300',
                )}
              >
                {f}
              </button>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusBadge status="online" label="Graph Synced" />
          <button className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-[rgba(0,212,255,0.08)] border border-[rgba(0,212,255,0.2)] text-[#00d4ff] text-xs font-medium hover:bg-[rgba(0,212,255,0.12)] transition-colors">
            <Plus className="w-3.5 h-3.5" />
            Add Node
          </button>
        </div>
      </div>

      <div className="flex flex-1 min-h-0">
        <div className="flex-1 min-w-0">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            nodeTypes={nodeTypes}
            fitView
            fitViewOptions={{ padding: 0.2 }}
            className="bg-transparent"
          >
            <Background variant={BackgroundVariant.Dots} gap={24} size={1} color="rgba(255,255,255,0.03)" />
            <Controls />
            <MiniMap nodeColor={(n) => categoryConfig[(n.data as { category: NodeCategory }).category]?.color ?? '#00d4ff'} />
          </ReactFlow>
        </div>

        <div className="w-64 shrink-0 border-l border-[rgba(255,255,255,0.06)] flex flex-col overflow-y-auto">
          <div className="p-4 border-b border-[rgba(255,255,255,0.06)]">
            <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Graph Stats</h3>
            <div className="grid grid-cols-2 gap-2">
              {stats.map((s) => {
                const Icon = s.icon
                return (
                  <div key={s.label} className="glass rounded-lg p-2.5">
                    <Icon className={cn('w-3.5 h-3.5 mb-1', s.color)} />
                    <div className={cn('text-sm font-bold font-mono', s.color)}>{s.value}</div>
                    <div className="text-[10px] text-zinc-600 mt-0.5">{s.label}</div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="p-4 border-b border-[rgba(255,255,255,0.06)]">
            <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Node Types</h3>
            <div className="space-y-2">
              {Object.entries(categoryConfig).map(([cat, cfg]) => (
                <div key={cat} className="flex items-center gap-2">
                  <div className="w-2 h-2 rounded-full" style={{ background: cfg.color }} />
                  <span className="text-xs text-zinc-500 capitalize">{cat}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="p-4">
            <h3 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-3">Recent Activity</h3>
            <div className="space-y-3">
              {recentMemories.map((m, i) => (
                <motion.div key={i} initial={{ opacity: 0, x: 8 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: i * 0.05 }} className="space-y-0.5">
                  <div className="text-xs text-zinc-400 leading-relaxed">{m.text}</div>
                  <div className="flex items-center gap-1.5">
                    <div className="w-1.5 h-1.5 rounded-full" style={{ background: categoryConfig[m.category].color }} />
                    <span className="text-[10px] text-zinc-700 font-mono">{m.time}</span>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
