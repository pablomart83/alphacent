import { useEffect, useMemo, useRef, useState } from 'react'
import {
  Activity,
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  Check,
  CheckCircle2,
  Pause,
  Play,
  ShieldBan,
  Sparkles,
  X,
  XCircle,
} from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Button, EmptyState } from '@/components/primitives'
import { wsManager } from '@/services/websocket'
import { cn, formatAge } from '@/lib/utils'

/**
 * LiveStream — unified rolling feed of the WS traffic that narrates the
 * autonomous cycle in real time. One buffer, filtered by chip.
 *
 *  - signal_generated          (green arrows, new signal)
 *  - autonomous_strategies     (proposed / backtested / activated / retired)
 *  - autonomous_cycle          (cycle start/complete)
 *  - cycle_progress            (stage transitions)
 *  - order_update              (fills / failures)
 *  - error                     (anything the backend broadcasts as error)
 */

type EventType =
  | 'signal'
  | 'strategy'
  | 'cycle'
  | 'stage'
  | 'order'
  | 'error'

interface StreamEvent {
  id: string
  timestamp: string
  type: EventType
  title: string
  detail: string
  accent: string
  Icon: React.ComponentType<{ className?: string; style?: React.CSSProperties }>
}

const FILTER_OPTIONS: Array<{ id: EventType | 'all'; label: string }> = [
  { id: 'all', label: 'All' },
  { id: 'signal', label: 'Signals' },
  { id: 'strategy', label: 'Strategies' },
  { id: 'cycle', label: 'Cycle' },
  { id: 'stage', label: 'Stages' },
  { id: 'order', label: 'Orders' },
  { id: 'error', label: 'Errors' },
]

const MAX_BUFFER = 100

export function LiveStream() {
  const [buffer, setBuffer] = useState<StreamEvent[]>([])
  const [filter, setFilter] = useState<EventType | 'all'>('all')
  const [paused, setPaused] = useState(false)
  const seqRef = useRef(0)

  const push = (evt: Omit<StreamEvent, 'id'>) => {
    if (paused) return
    setBuffer((prev) => {
      const id = `${Date.now()}-${seqRef.current++}`
      const next = [{ id, ...evt }, ...prev]
      return next.slice(0, MAX_BUFFER)
    })
  }

  // WS subscriptions
  useEffect(() => {
    const off: Array<() => void> = []

    off.push(
      wsManager.on('signal_generated', (data: any) => {
        const action = String(data?.action || '').toUpperCase()
        const isSell = action.includes('SELL') || action.includes('SHORT')
        const isExit = action.includes('EXIT')
        const conviction =
          typeof data?.confidence === 'number'
            ? ` · ${(data.confidence * 100).toFixed(0)}`
            : ''
        const strategyName = data?.strategy_name || ''
        const reasoning = data?.reasoning || ''
        // Show strategy name if available, otherwise truncate reasoning
        const detail = strategyName || (reasoning.length > 60 ? reasoning.slice(0, 60) + '…' : reasoning)
        push({
          timestamp: new Date().toISOString(),
          type: 'signal',
          title: `${data?.symbol || '?'} ${isExit ? 'EXIT' : isSell ? 'SELL' : 'BUY'}${conviction}`,
          detail,
          accent: isExit ? 'var(--text-2)' : isSell ? 'var(--pnl-down)' : 'var(--pnl-up)',
          Icon: isSell ? ArrowDownRight : ArrowUpRight,
        })
      }),
    )

    off.push(
      wsManager.on('autonomous_strategies', (data: any) => {
        const event = String(data?.event || data?.type || '').toLowerCase()
        const strategyName =
          data?.strategy?.name ||
          data?.data?.strategy?.name ||
          data?.strategy_name ||
          data?.name ||
          'Strategy'
        const symbol = data?.strategy?.symbols?.[0] || data?.symbol || ''
        const sharpe = data?.strategy?.backtest_results?.sharpe_ratio ?? data?.sharpe ?? null
        const label = friendlyStrategyEvent(event)
        const detail = [
          label,
          symbol ? symbol : null,
          sharpe != null ? `Sharpe ${Number(sharpe).toFixed(2)}` : null,
        ].filter(Boolean).join(' · ')
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'strategy',
          title: strategyName,
          detail,
          accent: accentForStrategyEvent(event),
          Icon: iconForStrategyEvent(event),
        })
      }),
    )

    off.push(
      wsManager.on('strategy_update', (data: any) => {
        const strategyName = data?.name || data?.strategy_name || 'Strategy'
        const status = data?.status ? ` → ${String(data.status).toUpperCase()}` : ''
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'strategy',
          title: strategyName,
          detail: `update${status}`,
          accent: 'var(--accent-primary)',
          Icon: Sparkles,
        })
      }),
    )

    off.push(
      wsManager.on('autonomous_cycle', (data: any) => {
        const event = String(data?.event || '').toLowerCase()
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'cycle',
          title: event.replace(/_/g, ' ') || 'Cycle event',
          detail: data?.data?.cycle_id || data?.cycle_id || '',
          accent:
            event === 'cycle_started'
              ? 'var(--accent-primary)'
              : event === 'cycle_completed'
                ? 'var(--pnl-up)'
                : 'var(--text-2)',
          Icon: Activity,
        })
      }),
    )

    off.push(
      wsManager.on('cycle_progress', (data: any) => {
        const stage = String(data?.stage_label || data?.stage || '').replace(/_/g, ' ')
        const status = String(data?.status || '').toLowerCase()
        if (!stage) return
        // Show starts, completions, and errors — completions are useful to confirm progress
        if (status !== 'running' && status !== 'complete' && status !== 'error' && status !== 'failed') return
        const isError = status === 'error' || status === 'failed'
        const isComplete = status === 'complete'
        // Build a detail line from metrics
        const metrics = data?.metrics || {}
        const metricParts: string[] = []
        if (metrics.proposed != null) metricParts.push(`${metrics.proposed} proposed`)
        if (metrics.backtested != null) metricParts.push(`${metrics.backtested} backtested`)
        if (metrics.passed != null) metricParts.push(`${metrics.passed} passed`)
        if (metrics.activated != null) metricParts.push(`${metrics.activated} activated`)
        if (metrics.signals != null || metrics.signals_generated != null) metricParts.push(`${metrics.signals ?? metrics.signals_generated} signals`)
        if (metrics.retired != null) metricParts.push(`${metrics.retired} retired`)
        if (metrics.cleaned != null) metricParts.push(`${metrics.cleaned} cleaned`)
        const detail = isError
          ? (data?.error || 'stage error')
          : metricParts.length > 0
            ? metricParts.join(' · ')
            : isComplete ? 'done' : 'running'
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'stage',
          title: `${isComplete ? '✓' : isError ? '✗' : '▶'} ${stage}`,
          detail,
          accent: isError
            ? 'var(--pnl-down)'
            : isComplete
              ? 'var(--pnl-up)'
              : 'var(--accent-primary)',
          Icon: isError ? AlertTriangle : isComplete ? CheckCircle2 : Activity,
        })
      }),
    )

    off.push(
      wsManager.on('order_update', (data: any) => {
        const symbol = data?.symbol || '?'
        const status = String(data?.status || '').toUpperCase()
        const side = String(data?.side || '').toUpperCase()
        const isFilled = status === 'FILLED'
        const isFailed = status === 'FAILED' || status === 'REJECTED' || status === 'CANCELLED'
        const isSubmitted = status === 'SUBMITTED' || status === 'PENDING'
        if (!isFilled && !isFailed && !isSubmitted) return
        const price = data?.filled_price ?? data?.price
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'order',
          title: `${symbol} ${side} ${status}`,
          detail:
            data?.strategy_name ||
            (price != null ? `@ ${Number(price).toFixed(2)}` : ''),
          accent: isFailed ? 'var(--pnl-down)' : isFilled ? 'var(--pnl-up)' : 'var(--text-2)',
          Icon: isFailed ? XCircle : isFilled ? CheckCircle2 : Activity,
        })
      }),
    )

    off.push(
      wsManager.on('error', (data: any) => {
        push({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'error',
          title: 'Error',
          detail:
            (typeof data === 'string' && data) ||
            data?.error?.message ||
            data?.message ||
            data?.error ||
            'unknown error',
          accent: 'var(--pnl-down)',
          Icon: ShieldBan,
        })
      }),
    )

    return () => {
      off.forEach((u) => u())
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused])

  const filtered = useMemo(() => {
    if (filter === 'all') return buffer
    return buffer.filter((e) => e.type === filter)
  }, [buffer, filter])

  return (
    <section className="flex flex-col gap-2 p-2 min-h-0 h-full">
      <div className="flex items-center gap-2">
        <SectionLabel>Live stream</SectionLabel>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setPaused((p) => !p)}
          aria-label={paused ? 'Resume stream' : 'Pause stream'}
          title={paused ? 'Resume stream' : 'Pause stream'}
          className="ml-auto"
        >
          {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
        </Button>
        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setBuffer([])}
          aria-label="Clear stream"
          title="Clear stream"
        >
          <X className="h-3 w-3" />
        </Button>
      </div>

      <div className="flex items-center gap-1 flex-wrap">
        {FILTER_OPTIONS.map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setFilter(opt.id)}
            className={cn(
              'h-5 px-1.5 rounded-[2px] text-[10px] font-medium uppercase tracking-wide transition-colors',
              filter === opt.id
                ? 'bg-[var(--bg-active)] text-[var(--text-0)]'
                : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
            )}
          >
            {opt.label}
          </button>
        ))}
        {paused && (
          <span className="ml-auto text-[10px] text-[var(--status-warning)] inline-flex items-center gap-1">
            <Pause className="h-2.5 w-2.5" />
            Paused · {buffer.length} events buffered
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-auto rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
        {filtered.length === 0 ? (
          <EmptyState
            title="No events yet"
            description="Live events stream here as the cycle fires. Watch this panel during scheduled runs."
            className="py-6"
          />
        ) : (
          <ul className="divide-y divide-[var(--border-subtle)]">
            {filtered.map((evt) => (
              <li
                key={evt.id}
                className="flex items-start gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)]"
              >
                <evt.Icon className="h-3 w-3 mt-[2px] shrink-0" style={{ color: evt.accent }} />
                <div className="flex-1 min-w-0">
                  <div className="text-[11px] text-[var(--text-0)] font-medium truncate" title={evt.title}>
                    {evt.title}
                  </div>
                  {evt.detail && (
                    <div
                      className="text-[10px] text-[var(--text-2)] truncate"
                      title={evt.detail}
                    >
                      {evt.detail}
                    </div>
                  )}
                </div>
                <span className="text-[10px] text-[var(--text-3)] mono shrink-0 pt-[2px]">
                  {formatAge(evt.timestamp)}
                </span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  )
}

function friendlyStrategyEvent(event: string): string {
  switch (event) {
    case 'strategy_proposed':
      return 'proposed'
    case 'strategy_backtested':
      return 'backtested'
    case 'strategy_activated':
      return 'activated'
    case 'strategy_retired':
      return 'retired'
    default:
      return event || 'update'
  }
}

function iconForStrategyEvent(event: string): React.ComponentType<{ className?: string; style?: React.CSSProperties }> {
  switch (event) {
    case 'strategy_activated':
      return Check
    case 'strategy_retired':
      return XCircle
    case 'strategy_backtested':
      return CheckCircle2
    default:
      return Sparkles
  }
}

function accentForStrategyEvent(event: string): string {
  switch (event) {
    case 'strategy_activated':
      return 'var(--pnl-up)'
    case 'strategy_retired':
      return 'var(--text-3)'
    case 'strategy_backtested':
      return 'var(--status-warning)'
    case 'strategy_proposed':
      return 'var(--accent-secondary)'
    default:
      return 'var(--accent-primary)'
  }
}
