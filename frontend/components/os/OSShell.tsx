'use client'

import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { CommandPalette } from './CommandPalette'
import { PermissionModal } from './PermissionModal'
import { useOSStore, type NavSection } from '@/lib/os-store'

// Page imports
import { DashboardPage } from '@/app/(os)/dashboard/DashboardPage'
import { ChatPage } from '@/app/(os)/chat/ChatPage'
import { VoicePage } from '@/app/(os)/voice/VoicePage'
import { MemoryPage } from '@/app/(os)/memory/MemoryPage'
import { FilesPage } from '@/app/(os)/files/FilesPage'
import { BrowserPage } from '@/app/(os)/browser/BrowserPage'
import { AgentsPage } from '@/app/(os)/agents/AgentsPage'
import { AutomationPage } from '@/app/(os)/automation/AutomationPage'
import { LogsPage } from '@/app/(os)/logs/LogsPage'
import { InsightsPage } from '@/app/(os)/insights/InsightsPage'
import { SettingsPage } from '@/app/(os)/settings/SettingsPage'

const pages: Record<NavSection, React.ComponentType> = {
  dashboard: DashboardPage,
  chat: ChatPage,
  voice: VoicePage,
  memory: MemoryPage,
  files: FilesPage,
  browser: BrowserPage,
  agents: AgentsPage,
  automation: AutomationPage,
  logs: LogsPage,
  insights: InsightsPage,
  settings: SettingsPage,
}

export function OSShell() {
  const activeSection = useOSStore((s) => s.activeSection)
  const ActivePage = pages[activeSection]

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-background dot-grid">
      <Sidebar />
      <div className="flex flex-col flex-1 min-w-0">
        <Topbar />
        <main className="flex-1 overflow-auto">
          <ActivePage />
        </main>
      </div>
      <CommandPalette />
      <PermissionModal />
    </div>
  )
}
