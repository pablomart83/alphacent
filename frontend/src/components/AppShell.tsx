import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { TopNavBar } from './trading/TopNavBar'
import { useAuthStatus } from '@/hooks/useAuth'
import { useWebSocketQueryBridge } from '@/hooks/useWebSocketQueryBridge'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
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
  useKeyboardShortcuts()

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
    </div>
  )
}
