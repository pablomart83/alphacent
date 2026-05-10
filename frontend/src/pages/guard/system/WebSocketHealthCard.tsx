import { useCallback } from 'react'
import { RefreshCw, Wifi, WifiOff } from 'lucide-react'
import { Button } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatAge } from '@/lib/utils'
import { useWebSocketState } from '@/hooks/useWebSocketState'
import { wsManager } from '@/services/websocket'

export function WebSocketHealthCard() {
  const info = useWebSocketState()

  const reconnect = useCallback(() => {
    try {
      wsManager.disconnect()
    } catch {
      /* ignore */
    }
    setTimeout(() => wsManager.connect(), 50)
  }, [])

  const state = String(info.state)
  const isOpen = state === 'open'
  const color = isOpen
    ? 'var(--pnl-up)'
    : state === 'connecting'
      ? 'var(--status-warning)'
      : 'var(--pnl-down)'
  const lastMessageIso =
    info.lastMessageAt != null ? new Date(info.lastMessageAt).toISOString() : null

  return (
    <section className="space-y-1.5">
      <SectionLabel>WebSocket</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 flex items-center gap-3">
        <span
          className={cn(
            'inline-flex items-center gap-1 px-1.5 h-[18px] rounded-[3px] text-[9px] font-semibold uppercase tracking-wider',
            state === 'connecting' && 'animate-pulse',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${color} 15%, transparent)`,
            color,
            border: `1px solid color-mix(in oklab, ${color} 40%, transparent)`,
          }}
        >
          {isOpen ? <Wifi className="h-3 w-3" /> : <WifiOff className="h-3 w-3" />}
          {state}
        </span>
        <div className="flex-1 text-[10px] text-[var(--text-3)] space-y-0.5">
          <div>
            Reconnect attempts:{' '}
            <span className="mono tabular-nums text-[var(--text-1)]">{info.attempt}</span>
          </div>
          <div>
            Last message:{' '}
            <span className="mono tabular-nums text-[var(--text-1)]">
              {formatAge(lastMessageIso) || '—'}
            </span>
          </div>
        </div>
        <Button
          size="sm"
          variant="secondary"
          onClick={reconnect}
          className="gap-1.5"
          disabled={state === 'connecting'}
        >
          <RefreshCw className="h-3 w-3" />
          Reconnect
        </Button>
      </div>
    </section>
  )
}
