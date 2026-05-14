import { useEffect, useRef, useState } from 'react'
import {
  Activity,
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
import { api } from '@/services/api'
import { wsManager } from '@/services/websocket'
import { cn, formatAge } from '@/lib/utils'

/**
 * LiveStream — two-tab panel:
 *
 *  Cycle Log  — structured timestamped log of cycle stage events (like v1).
 *               Shows ▶ start, ✓ complete with metrics, ✗ errors.
 *               This is the default tab — most useful during a cycle run.
 *
 *  Events     — rolling WS feed of signals, strategy updates, orders.
 *               Filtered by chip. Useful for watching signal generation.
 */

// ── Cycle Log ──────────────────────────────────────────────────────────────

interface LogLine {
  id: string
  time: string
  message: string
  type: 'info' | 'success' | 'error' | 'signal' | 'order'
}

const STAGE_LABELS: Record<string, string> = {
  cache_warming: 'Cache warming',
  cleanup_retirement: 'Cleanup & retirement',
  performance_feedback: 'Performance feedback',
  strategy_proposals: 'Strategy proposals',
  data_validation: 'Data validation',
  walk_forward_backtesting: 'Walk-forward backtesting',
  strategy_activation: 'Strategy activation',
  signal_generation: 'Signal generation',
  order_submission: 'Order submission',
}

function stageLabel(key: string): string {
  return STAGE_LABELS[key] || key.replace(/_/g, ' ')
}

function metricsLine(metrics: Record<string, unknown>): string {
  const parts: string[] = []
  const pairs: Array<[string, string]> = [
    ['proposed', 'proposed'],
    ['backtested', 'backtested'],
    ['passed', 'passed'],
    ['activated', 'activated'],
    ['signals', 'signals'],
    ['signals_generated', 'signals'],
    ['orders_submitted', 'orders'],
    ['retired', 'retired'],
    ['cleaned', 'cleaned'],
    ['trades_analyzed', 'trades analyzed'],
    ['symbols_checked', 'symbols'],
  ]
  for (const [key, label] of pairs) {
    const v = metrics[key]
    if (typeof v === 'number' && v > 0) {
      parts.push(`${v} ${label}`)
    }
  }
  // avg_sharpe
  if (typeof metrics.avg_sharpe === 'number' && metrics.avg_sharpe > 0) {
    parts.push(`avg Sharpe ${metrics.avg_sharpe.toFixed(2)}`)
  }
  return parts.join(' · ')
}

function nowTime(): string {
  return new Date().toTimeString().slice(0, 8)
}

// ── Event Feed ─────────────────────────────────────────────────────────────

type EventType = 'signal' | 'strategy' | 'cycle' | 'order' | 'error'

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
  { id: 'order', label: 'Orders' },
  { id: 'error', label: 'Errors' },
]

const MAX_BUFFER = 100
const MAX_LOG = 200

// ── Component ──────────────────────────────────────────────────────────────

export function LiveStream() {
  const [tab, setTab] = useState<'log' | 'events'>('log')

  // Cycle log state
  const [log, setLog] = useState<LogLine[]>([])
  const logEndRef = useRef<HTMLDivElement>(null)
  const seqLog = useRef(0)
  // Track whether we've loaded the persisted log — avoid double-loading
  const persistedLoaded = useRef(false)

  const pushLog = (message: string, type: LogLine['type'] = 'info') => {
    setLog((prev) => {
      const id = `l-${Date.now()}-${seqLog.current++}`
      const next = [...prev, { id, time: nowTime(), message, type }]
      return next.slice(-MAX_LOG)
    })
  }

  // On mount: fetch the last cycle's persisted log from disk so the panel
  // shows the previous run even after navigating away or refreshing.
  useEffect(() => {
    if (persistedLoaded.current) return
    persistedLoaded.current = true
    api
      .get<{ lines: Array<{ id: string; message: string; type: LogLine['type'] }>; cycle_id: string | null }>(
        '/strategies/autonomous/cycle-log?lines=500',
      )
      .then((data) => {
        if (data.lines && data.lines.length > 0) {
          setLog(
            data.lines.map((l, i) => ({
              id: `hist-${i}`,
              time: '',   // historical lines don't have a separate time field — message contains it
              message: l.message,
              type: l.type,
            })),
          )
        }
      })
      .catch(() => {
        // Non-critical — panel just starts empty
      })
  }, [])

  // Event feed state
  const [buffer, setBuffer] = useState<StreamEvent[]>([])
  const [filter, setFilter] = useState<EventType | 'all'>('all')
  const [paused, setPaused] = useState(false)
  const seqEvt = useRef(0)

  const pushEvt = (evt: Omit<StreamEvent, 'id'>) => {
    if (paused) return
    setBuffer((prev) => {
      const id = `e-${Date.now()}-${seqEvt.current++}`
      return [{ id, ...evt }, ...prev].slice(0, MAX_BUFFER)
    })
  }

  // Auto-scroll log to bottom
  useEffect(() => {
    if (tab === 'log' && logEndRef.current) {
      logEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [log, tab])

  // WS subscriptions
  useEffect(() => {
    const off: Array<() => void> = []

    // ── cycle_progress → Cycle Log ──────────────────────────────────────
    off.push(
      wsManager.on('cycle_progress', (data: any) => {
        const stage = String(data?.stage || '')
        const status = String(data?.status || '').toLowerCase()
        const metrics: Record<string, unknown> = data?.metrics || {}
        const label = stageLabel(stage)
        const phase = metrics?.phase as string | undefined

        if (status === 'running') {
          // Suppress per-strategy iteration messages (e.g. "Walk-forward X (79/192)")
          // except every 20th one — gives progress without flooding.
          const iterMatch = phase && phase.match(/\((\d+)\/(\d+)\)/)
          if (iterMatch) {
            const current = parseInt(iterMatch[1], 10)
            const total = parseInt(iterMatch[2], 10)
            const isLast = current === total
            const isEvery20 = current % 20 === 0
            if (!isEvery20 && !isLast) return // suppress
          }
          pushLog(`▶ ${label}${phase ? ` — ${phase}` : ''}`, 'info')
        } else if (status === 'complete') {
          const detail = metricsLine(metrics)
          pushLog(`✓ ${label}${detail ? ` — ${detail}` : ''}`, 'success')
        } else if (status === 'error' || status === 'failed') {
          pushLog(`✗ ${label}: ${data?.error || 'error'}`, 'error')
        }
      }),
    )

    // ── autonomous_cycle → Cycle Log ────────────────────────────────────
    off.push(
      wsManager.on('autonomous_cycle', (data: any) => {
        const event = String(data?.event || '').toLowerCase()
        if (event === 'cycle_started') {
          setLog([]) // clear log on new cycle
          pushLog('━━ Cycle started ━━', 'info')
        } else if (event === 'cycle_completed') {
          pushLog('━━ Cycle complete ━━', 'success')
        } else if (event === 'cycle_failed' || event === 'cycle_error') {
          pushLog(`━━ Cycle failed: ${data?.error || 'unknown error'} ━━`, 'error')
        }
      }),
    )

    // ── signal_generated → both tabs ────────────────────────────────────
    off.push(
      wsManager.on('signal_generated', (data: any) => {
        const action = String(data?.action || '').toUpperCase()
        const isSell = action.includes('SELL') || action.includes('SHORT')
        const isExit = action.includes('EXIT')
        const conviction = typeof data?.confidence === 'number'
          ? ` · ${(data.confidence * 100).toFixed(0)}`
          : ''
        const strategyName = data?.strategy_name || ''

        // Cycle log: compact one-liner
        pushLog(
          `${isExit ? '↩' : isSell ? '↓' : '↑'} ${data?.symbol || '?'} ${isExit ? 'EXIT' : isSell ? 'SELL' : 'BUY'}${conviction}${strategyName ? ` · ${strategyName}` : ''}`,
          isExit ? 'info' : 'signal',
        )

        // Event feed
        pushEvt({
          timestamp: new Date().toISOString(),
          type: 'signal',
          title: `${data?.symbol || '?'} ${isExit ? 'EXIT' : isSell ? 'SELL' : 'BUY'}${conviction}`,
          detail: strategyName || (data?.reasoning ? String(data.reasoning).slice(0, 60) : ''),
          accent: isExit ? 'var(--text-2)' : isSell ? 'var(--pnl-down)' : 'var(--pnl-up)',
          Icon: isSell ? ArrowDownRight : ArrowUpRight,
        })
      }),
    )

    // ── autonomous_strategies → event feed only ──────────────────────────
    // Batch strategy_proposed events — don't flood with 200 individual proposals
    off.push(
      wsManager.on('autonomous_strategies', (data: any) => {
        const event = String(data?.event || data?.type || '').toLowerCase()
        const name = data?.strategy?.name || data?.strategy_name || data?.name || 'Strategy'
        const symbol = data?.strategy?.symbols?.[0] || data?.symbol || ''
        const sharpe = data?.strategy?.backtest_results?.sharpe_ratio ?? data?.sharpe ?? null
        const label = friendlyStrategyEvent(event)
        // Skip individual proposal events — they flood the stream (200 per cycle)
        if (event === 'strategy_proposed') return
        const detail = [label, symbol || null, sharpe != null ? `Sharpe ${Number(sharpe).toFixed(2)}` : null].filter(Boolean).join(' · ')
        pushEvt({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'strategy',
          title: name,
          detail,
          accent: accentForStrategyEvent(event),
          Icon: iconForStrategyEvent(event),
        })
      }),
    )

    // ── order_update → both tabs ─────────────────────────────────────────
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
        const priceStr = price != null ? ` @ ${Number(price).toFixed(2)}` : ''

        // Cycle log: only fills and failures
        if (isFilled || isFailed) {
          pushLog(
            `${isFilled ? '✓' : '✗'} Order ${symbol} ${side} ${status}${priceStr}`,
            isFilled ? 'order' : 'error',
          )
        }

        pushEvt({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'order',
          title: `${symbol} ${side} ${status}`,
          detail: data?.strategy_name || priceStr.trim(),
          accent: isFailed ? 'var(--pnl-down)' : isFilled ? 'var(--pnl-up)' : 'var(--text-2)',
          Icon: isFailed ? XCircle : isFilled ? CheckCircle2 : Activity,
        })
      }),
    )

    // ── error → event feed ───────────────────────────────────────────────
    off.push(
      wsManager.on('error', (data: any) => {
        const msg = (typeof data === 'string' && data) || data?.error?.message || data?.message || data?.error || 'unknown error'
        pushEvt({
          timestamp: data?.timestamp || new Date().toISOString(),
          type: 'error',
          title: 'Error',
          detail: msg,
          accent: 'var(--pnl-down)',
          Icon: ShieldBan,
        })
      }),
    )

    return () => off.forEach((u) => u())
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [paused])

  const filtered = filter === 'all' ? buffer : buffer.filter((e) => e.type === filter)

  return (
    <section className="flex flex-col gap-0 min-h-0 h-full">
      {/* Tab bar */}
      <div className="flex items-center gap-0 px-2 pt-2 pb-0 shrink-0">
        <SectionLabel className="mr-auto">Live stream</SectionLabel>
        <div className="flex items-center gap-0 border border-[var(--border-subtle)] rounded-[3px] overflow-hidden">
          {(['log', 'events'] as const).map((t) => (
            <button
              key={t}
              type="button"
              onClick={() => setTab(t)}
              className={cn(
                'h-5 px-2 text-[10px] font-medium uppercase tracking-wide transition-colors',
                tab === t
                  ? 'bg-[var(--bg-active)] text-[var(--text-0)]'
                  : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
              )}
            >
              {t === 'log' ? 'Cycle log' : 'Events'}
            </button>
          ))}
        </div>
      </div>

      {/* Cycle Log tab */}
      {tab === 'log' && (
        <div className="flex-1 min-h-0 flex flex-col gap-1 p-2">
          <div className="flex-1 min-h-0 overflow-auto rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] font-mono text-[10px]">
            {log.length === 0 ? (
              <EmptyState
                title="No cycle activity yet"
                description="Stage events stream here when a cycle runs. Trigger one from the left panel."
                className="py-6"
              />
            ) : (
              <div className="p-1.5 flex flex-col gap-0.5">
                {log.map((line) => (
                  <div key={line.id} className="flex items-start gap-1.5 leading-[1.4]">
                    {line.time && (
                      <span className="text-[var(--text-3)] shrink-0 tabular-nums">{line.time}</span>
                    )}
                    <span
                      className={cn(
                        'flex-1 min-w-0 break-words',
                        line.type === 'success' && 'text-[var(--pnl-up)]',
                        line.type === 'error' && 'text-[var(--pnl-down)]',
                        line.type === 'signal' && 'text-[var(--accent-primary)]',
                        line.type === 'order' && 'text-[var(--status-warning)]',
                        line.type === 'info' && 'text-[var(--text-1)]',
                      )}
                    >
                      {line.message}
                    </span>
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            )}
          </div>
          <button
            type="button"
            onClick={() => setLog([])}
            className="self-end text-[9px] text-[var(--text-3)] hover:text-[var(--text-1)] transition-colors"
          >
            Clear log
          </button>
        </div>
      )}

      {/* Events tab */}
      {tab === 'events' && (
        <div className="flex-1 min-h-0 flex flex-col gap-1 p-2">
          <div className="flex items-center gap-1 flex-wrap shrink-0">
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
            <div className="ml-auto flex items-center gap-1">
              <Button variant="ghost" size="icon-sm" onClick={() => setPaused((p) => !p)} title={paused ? 'Resume' : 'Pause'}>
                {paused ? <Play className="h-3 w-3" /> : <Pause className="h-3 w-3" />}
              </Button>
              <Button variant="ghost" size="icon-sm" onClick={() => setBuffer([])} title="Clear">
                <X className="h-3 w-3" />
              </Button>
            </div>
          </div>
          {paused && (
            <span className="text-[10px] text-[var(--status-warning)] inline-flex items-center gap-1 shrink-0">
              <Pause className="h-2.5 w-2.5" /> Paused · {buffer.length} buffered
            </span>
          )}
          <div className="flex-1 min-h-0 overflow-auto rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
            {filtered.length === 0 ? (
              <EmptyState
                title="No events yet"
                description="Signals, strategy updates, and orders appear here in real time."
                className="py-6"
              />
            ) : (
              <ul className="divide-y divide-[var(--border-subtle)]">
                {filtered.map((evt) => (
                  <li key={evt.id} className="flex items-start gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)]">
                    <evt.Icon className="h-3 w-3 mt-[2px] shrink-0" style={{ color: evt.accent }} />
                    <div className="flex-1 min-w-0">
                      <div className="text-[11px] text-[var(--text-0)] font-medium truncate" title={evt.title}>{evt.title}</div>
                      {evt.detail && <div className="text-[10px] text-[var(--text-2)] truncate" title={evt.detail}>{evt.detail}</div>}
                    </div>
                    <span className="text-[10px] text-[var(--text-3)] mono shrink-0 pt-[2px]">{formatAge(evt.timestamp)}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  )
}

function friendlyStrategyEvent(event: string): string {
  switch (event) {
    case 'strategy_proposed': return 'proposed'
    case 'strategy_backtested': return 'backtested'
    case 'strategy_activated': return 'activated'
    case 'strategy_retired': return 'retired'
    default: return event || 'update'
  }
}

function iconForStrategyEvent(event: string): React.ComponentType<{ className?: string; style?: React.CSSProperties }> {
  switch (event) {
    case 'strategy_activated': return Check
    case 'strategy_retired': return XCircle
    case 'strategy_backtested': return CheckCircle2
    default: return Sparkles
  }
}

function accentForStrategyEvent(event: string): string {
  switch (event) {
    case 'strategy_activated': return 'var(--pnl-up)'
    case 'strategy_retired': return 'var(--text-3)'
    case 'strategy_backtested': return 'var(--status-warning)'
    case 'strategy_proposed': return 'var(--accent-secondary)'
    default: return 'var(--accent-primary)'
  }
}
