'use client'

import { motion, AnimatePresence } from 'framer-motion'
import { Shield, AlertTriangle, Check, X, ShieldCheck } from 'lucide-react'
import { usePermissions } from '@/lib/hooks/use-permissions'
import { cn } from '@/lib/utils'

export function PermissionModal() {
  const { pending, grant, deny, addAutoApprove } = usePermissions()

  const activeRequest = pending.data?.pending?.[0]

  if (!activeRequest) return null

  const handleGrant = () => {
    grant.mutate(activeRequest.id)
  }

  const handleDeny = () => {
    deny.mutate(activeRequest.id)
  }

  const handleAlwaysAllow = () => {
    // Register the action as an auto-approve pattern
    addAutoApprove.mutate(activeRequest.action, {
      onSuccess: () => {
        // Once registered, grant this request
        grant.mutate(activeRequest.id)
      }
    })
  }

  return (
    <AnimatePresence>
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
        <motion.div
          initial={{ opacity: 0, scale: 0.95, y: 10 }}
          animate={{ opacity: 1, scale: 1, y: 0 }}
          exit={{ opacity: 0, scale: 0.95, y: 10 }}
          transition={{ duration: 0.25, ease: 'easeOut' }}
          className="w-full max-w-lg overflow-hidden rounded-2xl border border-[rgba(255,255,255,0.08)] bg-[#0c0c0e]/95 backdrop-blur-md shadow-2xl"
        >
          {/* Header */}
          <div className="flex items-center gap-3 p-4 border-b border-[rgba(255,255,255,0.06)] bg-[rgba(245,158,11,0.03)]">
            <div className="p-2 rounded-lg bg-[rgba(245,158,11,0.1)] border border-[rgba(245,158,11,0.2)]">
              <Shield className="w-5 h-5 text-[#f59e0b]" />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-zinc-100 font-mono uppercase tracking-wider">
                Permission Request
              </h2>
              <p className="text-[10px] text-zinc-500 font-mono mt-0.5">
                SOURCE: {activeRequest.source_module}
              </p>
            </div>
          </div>

          {/* Body */}
          <div className="p-5 space-y-4 max-h-[380px] overflow-y-auto">
            {/* Action explanation */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-widest text-zinc-500 mb-1">
                Requested Action
              </div>
              <div className="text-sm font-mono text-zinc-300 bg-[rgba(255,255,255,0.02)] p-2.5 rounded-lg border border-[rgba(255,255,255,0.05)]">
                {activeRequest.action}
              </div>
            </div>

            {/* Why (Reasoning) */}
            <div>
              <div className="text-[10px] uppercase font-mono tracking-widest text-zinc-500 mb-1">
                Reasoning (Why)
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">
                {activeRequest.reasoning}
              </p>
            </div>

            {/* Benefits & Risks side-by-side */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {/* Benefits */}
              <div className="p-3 rounded-xl bg-[rgba(34,197,94,0.03)] border border-[rgba(34,197,94,0.1)]">
                <div className="text-[10px] uppercase font-mono tracking-wider text-[#22c55e] mb-1.5 flex items-center gap-1">
                  <Check className="w-3 h-3" /> Benefits
                </div>
                {activeRequest.benefits && activeRequest.benefits.length > 0 ? (
                  <ul className="text-[11px] text-zinc-400 space-y-1 list-disc pl-3">
                    {activeRequest.benefits.map((b: string, i: number) => (
                      <li key={i}>{b}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-[11px] text-zinc-600 italic">No benefits listed</div>
                )}
              </div>

              {/* Risks */}
              <div className="p-3 rounded-xl bg-[rgba(239,68,68,0.03)] border border-[rgba(239,68,68,0.1)]">
                <div className="text-[10px] uppercase font-mono tracking-wider text-[#ef4444] mb-1.5 flex items-center gap-1">
                  <AlertTriangle className="w-3 h-3" /> Risks
                </div>
                {activeRequest.risks && activeRequest.risks.length > 0 ? (
                  <ul className="text-[11px] text-zinc-400 space-y-1 list-disc pl-3">
                    {activeRequest.risks.map((r: string, i: number) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : (
                  <div className="text-[11px] text-zinc-600 italic">No risks listed</div>
                )}
              </div>
            </div>

            {/* Alternatives */}
            {activeRequest.alternatives && activeRequest.alternatives.length > 0 && (
              <div>
                <div className="text-[10px] uppercase font-mono tracking-widest text-zinc-500 mb-1">
                  Alternatives Considered
                </div>
                <ul className="text-[11px] text-zinc-400 space-y-1 list-disc pl-4 leading-relaxed">
                  {activeRequest.alternatives.map((alt: string, i: number) => (
                    <li key={i}>{alt}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>

          {/* Footer actions */}
          <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-3 p-4 border-t border-[rgba(255,255,255,0.06)] bg-[rgba(0,0,0,0.2)]">
            <button
              onClick={handleAlwaysAllow}
              className="flex items-center justify-center gap-1.5 px-3.5 py-1.5 rounded-lg border border-[rgba(34,197,94,0.2)] bg-[rgba(34,197,94,0.05)] text-[#22c55e] text-xs font-semibold hover:bg-[rgba(34,197,94,0.09)] transition-colors text-center"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              Always Allow
            </button>
            <div className="flex items-center gap-2">
              <button
                onClick={handleDeny}
                className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-4 py-1.5 rounded-lg bg-[rgba(239,68,68,0.08)] border border-[rgba(239,68,68,0.2)] text-[#ef4444] text-xs font-semibold hover:bg-[rgba(239,68,68,0.12)] transition-colors"
              >
                <X className="w-3.5 h-3.5" />
                Deny
              </button>
              <button
                onClick={handleGrant}
                className="flex-1 sm:flex-none flex items-center justify-center gap-1.5 px-5 py-1.5 rounded-lg bg-[#00d4ff] text-[#09090b] text-xs font-bold hover:bg-[#00b0d4] transition-colors shadow-[0_0_12px_rgba(0,212,255,0.3)]"
              >
                <Check className="w-3.5 h-3.5" />
                Grant Once
              </button>
            </div>
          </div>
        </motion.div>
      </div>
    </AnimatePresence>
  )
}
