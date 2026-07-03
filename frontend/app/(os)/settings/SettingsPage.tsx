'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { GlassCard } from '@/components/os/GlassCard'
import { Settings, Bell, Shield, Palette, Keyboard, Puzzle, User, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'

const sections = [
  { id: 'general', label: 'General', icon: Settings, desc: 'Language, region, startup behavior' },
  { id: 'appearance', label: 'Appearance', icon: Palette, desc: 'Theme, density, animations' },
  { id: 'notifications', label: 'Notifications', icon: Bell, desc: 'Alert preferences, sounds' },
  { id: 'privacy', label: 'Privacy & Security', icon: Shield, desc: 'Permissions, encryption, data controls' },
  { id: 'shortcuts', label: 'Keyboard Shortcuts', icon: Keyboard, desc: 'Custom key bindings' },
  { id: 'account', label: 'Account', icon: User, desc: 'Profile, billing, API keys' },
  { id: 'extensions', label: 'Extensions', icon: Puzzle, desc: 'Plugins and integrations' },
]

export function SettingsPage() {
  const [active, setActive] = useState('general')

  return (
    <div className="flex h-full">
      <div className="w-60 shrink-0 border-r border-[rgba(255,255,255,0.06)] p-4">
        <h2 className="text-xs font-mono uppercase tracking-widest text-zinc-600 mb-4">Settings</h2>
        <div className="space-y-1">
          {sections.map((s) => {
            const Icon = s.icon
            return (
              <button
                key={s.id}
                onClick={() => setActive(s.id)}
                className={cn(
                  'w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-left transition-colors',
                  active === s.id ? 'bg-[rgba(0,212,255,0.08)] text-[#00d4ff]' : 'text-zinc-400 hover:text-zinc-200 hover:bg-[rgba(255,255,255,0.03)]',
                )}
              >
                <Icon className="w-4 h-4" />
                <div className="flex-1">
                  <div className="text-sm font-medium">{s.label}</div>
                  <div className="text-[10px] text-zinc-600">{s.desc}</div>
                </div>
                <ChevronRight className="w-3 h-3 text-zinc-700" />
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center">
        <div className="text-center space-y-2">
          <Settings className="w-12 h-12 mx-auto text-zinc-700" />
          <p className="text-sm text-zinc-600">Settings panel coming soon</p>
          <p className="text-xs text-zinc-700">Select a category to configure</p>
        </div>
      </div>
    </div>
  )
}
