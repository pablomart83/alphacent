import { useWebSocketState } from '@/hooks/useWebSocketState'
import { wsManager } from '@/services/websocket'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/primitives'
import { cn, formatAge } from '@/lib/utils'

export function WebSocketIndicator() {
  const { state, attempt, lastMessageAt } = useWebSocketState()

  const color =
    state === 'open'
      ? 'bg-[var(--pnl-up)]'
      : state === 'connecting'
        ? 'bg-[var(--status-warning)] animate-pulse'
        : 'bg-[var(--pnl-down)]'

  const label =
    state === 'open'
      ? 'Live'
      : state === 'connecting'
        ? `Reconnecting${attempt > 0 ? ` (${attempt})` : ''}`
        : 'Offline'

  return (
    <TooltipProvider delayDuration={300}>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            onClick={() => wsManager.forceReconnect()}
            aria-label={`WebSocket ${label} — click to reconnect`}
            className="inline-flex items-center gap-1.5 px-1.5 py-0.5 rounded-[2px] hover:bg-[var(--bg-hover)] transition-colors"
          >
            <span className={cn('h-1.5 w-1.5 rounded-full', color)} aria-hidden />
            <span className="text-[10px] text-[var(--text-2)] font-medium">{label}</span>
          </button>
        </TooltipTrigger>
        <TooltipContent>
          <div className="flex flex-col gap-0.5">
            <span>WebSocket: {state}</span>
            {lastMessageAt && (
              <span className="text-[var(--text-2)]">
                Last message: {formatAge(new Date(lastMessageAt))}
              </span>
            )}
            {state !== 'open' && <span className="text-[var(--text-2)]">Click to reconnect</span>}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  )
}
