import { useEffect } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { wsManager } from '@/services/websocket'
import { toast } from 'sonner'

/**
 * Bridges WebSocket events into TanStack Query cache invalidation.
 * Mounted once inside AppShell.
 */
export function useWebSocketQueryBridge() {
  const qc = useQueryClient()

  useEffect(() => {
    const unsubs: Array<() => void> = []

    unsubs.push(
      wsManager.on('position_update', () => {
        qc.invalidateQueries({ queryKey: ['positions'] })
        qc.invalidateQueries({ queryKey: ['account-info'] })
        qc.invalidateQueries({ queryKey: ['dashboard'] })
      }),
    )

    unsubs.push(
      wsManager.on('order_update', () => {
        qc.invalidateQueries({ queryKey: ['orders'] })
        qc.invalidateQueries({ queryKey: ['dashboard'] })
      }),
    )

    unsubs.push(
      wsManager.on('strategy_update', () => {
        qc.invalidateQueries({ queryKey: ['strategies'] })
        qc.invalidateQueries({ queryKey: ['dashboard'] })
      }),
    )

    unsubs.push(
      wsManager.on('system_state', () => {
        qc.invalidateQueries({ queryKey: ['system-status'] })
      }),
    )

    unsubs.push(
      wsManager.on('autonomous_status', () => {
        qc.invalidateQueries({ queryKey: ['autonomous-status'] })
      }),
    )

    unsubs.push(
      wsManager.on('autonomous_cycle', () => {
        qc.invalidateQueries({ queryKey: ['autonomous-cycles'] })
        qc.invalidateQueries({ queryKey: ['autonomous-status'] })
      }),
    )

    unsubs.push(
      wsManager.on('fundamental_alert', () => {
        qc.invalidateQueries({ queryKey: ['fundamental-alerts'] })
      }),
    )

    // Signal pushes: invalidate the /signals/recent cache so the SignalFeed
    // seed stays honest across reconnects / rejections, on top of the direct
    // subscription inside the feed component for the rolling buffer.
    unsubs.push(
      wsManager.on('signal_generated', () => {
        qc.invalidateQueries({ queryKey: ['recent-signals'] })
        qc.invalidateQueries({ queryKey: ['dashboard-recent-signals'] })
      }),
    )

    // On reconnect, refresh top-level queries and notify the user.
    let wasOpen = false
    let offlineSince: number | null = null
    unsubs.push(
      wsManager.onStateChange((state) => {
        if (state === 'closed' && wasOpen) {
          offlineSince = Date.now()
        }
        if (state === 'open' && offlineSince) {
          const downSec = Math.round((Date.now() - offlineSince) / 1000)
          toast.success(`Reconnected after ${downSec}s — data refreshed`)
          qc.invalidateQueries({ queryKey: ['positions'] })
          qc.invalidateQueries({ queryKey: ['orders'] })
          qc.invalidateQueries({ queryKey: ['strategies'] })
          qc.invalidateQueries({ queryKey: ['account-info'] })
          qc.invalidateQueries({ queryKey: ['autonomous-status'] })
          qc.invalidateQueries({ queryKey: ['system-status'] })
          qc.invalidateQueries({ queryKey: ['dashboard'] })
          qc.invalidateQueries({ queryKey: ['analytics-performance'] })
          qc.invalidateQueries({ queryKey: ['live-summary'] })
          qc.invalidateQueries({ queryKey: ['recent-signals'] })
          offlineSince = null
        }
        wasOpen = state === 'open'
      }),
    )

    return () => {
      unsubs.forEach((u) => u())
    }
  }, [qc])
}
