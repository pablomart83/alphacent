import { useEffect } from 'react'
import { Outlet } from 'react-router-dom'
import { TopNavBar } from './trading/TopNavBar'
import { useAuthStatus } from '@/hooks/useAuth'
import { useWebSocketQueryBridge } from '@/hooks/useWebSocketQueryBridge'
import { useKeyboardShortcuts } from '@/hooks/useKeyboardShortcuts'
import { wsManager } from '@/services/websocket'

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

  return (
    <div className="flex flex-col h-screen min-h-0 overflow-hidden bg-[var(--bg-0)]">
      <TopNavBar liveEnabled={false /* Sprint 1 will wire via /live/summary */} />
      <main className="flex-1 min-h-0 overflow-hidden">
        <Outlet />
      </main>
    </div>
  )
}
