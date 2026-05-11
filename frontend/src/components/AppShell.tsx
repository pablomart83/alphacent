import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { TopNavBar } from './trading/TopNavBar'
import { CommandPalette } from './CommandPalette'
import { NotificationDrawer } from './NotificationDrawer'
import { KeyboardShortcutHelp } from './KeyboardShortcutHelp'
import { useAuthStatus } from '@/hooks/useAuth'
import { useWebSocketQueryBridge } from '@/hooks/useWebSocketQueryBridge'
import { useAutonomousNotifications } from '@/hooks/useAutonomousNotifications'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { useUiOverlays } from '@/stores'
import { wsManager } from '@/services/websocket'
import { api } from '@/services/api'

interface LiveSummaryShape {
  active_live_authorizations: number
  live_enabled: boolean
}

export function AppShell() {
  const { data: auth } = useAuthStatus()

  // Connect / disconnect WS based on auth state
  useEffect(() => {
    if (auth?.authenticated) {
      wsManager.connect()
    }
    return () => {
      // Don't disconnect on every render — only on unmount (logout flow handles this)
    }
  }, [auth?.authenticated])

  useWebSocketQueryBridge()
  useAutonomousNotifications()
  useKeyboardShortcuts()

  const notificationsOpen = useUiOverlays((s) => s.notificationsOpen)
  const setNotificationsOpen = useUiOverlays((s) => s.setNotificationsOpen)
  const shortcutHelpOpen = useUiOverlays((s) => s.shortcutHelpOpen)
  const setShortcutHelpOpen = useUiOverlays((s) => s.setShortcutHelpOpen)

  // Single shared /live/summary query — keyed so Command page + TopNavBar share cache.
  const { data: liveSummary } = useQuery<LiveSummaryShape>({
    queryKey: ['live-summary'],
    queryFn: () => api.get<LiveSummaryShape>('/live/summary'),
    refetchInterval: 15_000,
    staleTime: 10_000,
    enabled: Boolean(auth?.authenticated),
  })

  return (
    <div className="flex flex-col h-screen min-h-0 overflow-hidden bg-[var(--bg-0)]">
      <TopNavBar liveEnabled={Boolean(liveSummary?.live_enabled)} />
      <main className="flex-1 min-h-0 overflow-hidden">
        <Outlet />
      </main>
      <CommandPalette />
      <NotificationDrawer
        open={notificationsOpen}
        onOpenChange={setNotificationsOpen}
      />
      <KeyboardShortcutHelp
        open={shortcutHelpOpen}
        onOpenChange={setShortcutHelpOpen}
      />
    </div>
  )
}
