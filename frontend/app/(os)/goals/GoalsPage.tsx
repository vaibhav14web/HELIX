'use client'

import React, { useState, useEffect } from 'react'
import { Target, CheckCircle2, Circle, Clock, Plus, Layers, AlertCircle } from 'lucide-react'
import { api } from '@/lib/api-client'

export default function GoalsPage() {
  const [goals, setGoals] = useState<any[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [newTitle, setNewTitle] = useState('')
  const [newDesc, setNewDesc] = useState('')
  const [newPriority, setNewPriority] = useState('medium')

  useEffect(() => {
    async function loadGoals() {
      try {
        const res = await api.goals.get()
        setGoals(res?.goals || [])
      } catch (err) {
        console.error('Failed loading goals:', err)
      } finally {
        setLoading(false)
      }
    }
    loadGoals()
  }, [])

  const handleCreateGoal = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!newTitle.strip()) return
    try {
      await api.goals.create({ title: newTitle, description: newDesc, priority: newPriority })
      const updated = await api.goals.get()
      setGoals(updated?.goals || [])
      setShowModal(false)
      setNewTitle('')
      setNewDesc('')
    } catch (err) {
      console.error('Failed creating goal:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full text-zinc-400">
        <Target className="w-6 h-6 animate-spin mr-2 text-indigo-400" />
        <span>Loading Long-Running Goals...</span>
      </div>
    )
  }

  return (
    <div className="h-full overflow-y-auto p-6 space-y-6 text-zinc-100 bg-zinc-950/40">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-zinc-100 flex items-center gap-2">
            <Target className="w-7 h-7 text-emerald-400" />
            Long-Running Goals & Milestones
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Track multi-step objective DAGs, subtask dependency progress, and persistent operational milestones.
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          className="flex items-center gap-2 bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded-xl text-xs font-semibold shadow-lg shadow-indigo-600/20 transition-all"
        >
          <Plus className="w-4 h-4" />
          <span>New Goal</span>
        </button>
      </div>

      {/* Goals Canvas List */}
      <div className="space-y-4">
        {goals.map((goal) => (
          <div key={goal.goal_id} className="p-5 rounded-2xl bg-zinc-900/60 border border-zinc-800/80 backdrop-blur-md space-y-4">
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-3">
                  <h3 className="text-base font-bold text-zinc-100">{goal.title}</h3>
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold uppercase bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                    {goal.priority} Priority
                  </span>
                </div>
                <p className="text-xs text-zinc-400 mt-1">{goal.description}</p>
              </div>
              <div className="text-right">
                <span className="text-xl font-extrabold text-indigo-400">{goal.progress_percent}%</span>
                <span className="text-[10px] text-zinc-500 block">Progress</span>
              </div>
            </div>

            {/* Progress Bar */}
            <div className="w-full bg-zinc-800/60 h-2 rounded-full overflow-hidden">
              <div
                className="bg-gradient-to-r from-indigo-500 to-emerald-400 h-full transition-all duration-500"
                style={{ width: `${goal.progress_percent}%` }}
              />
            </div>

            {/* Subtask DAG Nodes */}
            <div className="space-y-2 pt-2">
              <span className="text-xs font-semibold text-zinc-400 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-zinc-500" /> Subtask Milestone Tree
              </span>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                {goal.tasks?.map((t: any) => (
                  <div key={t.task_id} className="p-3 bg-zinc-800/30 rounded-xl border border-zinc-800/60 flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      {t.status === 'completed' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                      ) : t.status === 'in_progress' ? (
                        <Clock className="w-4 h-4 text-indigo-400 animate-pulse" />
                      ) : (
                        <Circle className="w-4 h-4 text-zinc-600" />
                      )}
                      <span className={t.status === 'completed' ? 'line-through text-zinc-500' : 'text-zinc-200'}>
                        {t.title}
                      </span>
                    </div>
                    <span className="text-[10px] capitalize font-mono text-zinc-400">{t.status}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* New Goal Modal */}
      {showModal && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4 z-50">
          <form onSubmit={handleCreateGoal} className="bg-zinc-900 border border-zinc-800 rounded-2xl p-6 w-full max-w-md space-y-4">
            <h2 className="text-lg font-bold text-zinc-100 flex items-center gap-2">
              <Target className="w-5 h-5 text-indigo-400" /> Create Long-Running Goal
            </h2>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">Goal Title</label>
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="e.g., Optimize Database Architecture"
                className="w-full bg-zinc-800/80 border border-zinc-700 rounded-xl p-2.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500"
                required
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-zinc-400 mb-1">Description</label>
              <textarea
                value={newDesc}
                onChange={(e) => setNewDesc(e.target.value)}
                placeholder="Details of objectives and milestones..."
                className="w-full bg-zinc-800/80 border border-zinc-700 rounded-xl p-2.5 text-xs text-zinc-100 focus:outline-none focus:border-indigo-500 h-24"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="px-4 py-2 rounded-xl text-xs font-semibold text-zinc-400 hover:text-zinc-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white"
              >
                Create Goal
              </button>
            </div>
          </form>
        </div>
      )}
    </div>
  )
}
