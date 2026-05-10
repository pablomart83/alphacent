import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { ArrowDownRight, ArrowUpRight, ShieldBan, Zap } from 'lucide-react'
import { api } from '@/services/api'
import { wsManager } from '@/services/websocket'
import { useTradingMode } from '@/stores'
import { formatAge, cn } from '@/lib/utils'
import { EmptyState, Skeleton } from '@/components/primitives'

/**
 * Signal feed — rolling 50-event buffer fed by a seed fetch to
 * `/signals/recent?limit=50` plus live `signal_generated` WebSocket pushes.
 *
 * Each row shows side (BUY/SELL), a decision dot (accepted=green,
 * rejected=amber, blocked=red), strategy, symbol and a truncated reason
 * tooltip. Filter chips: entries only, exits only, rejections only.
 */

interface SignalRow {
  id: string
  timestamp: string
  symbol: string
  strategyName: string | null
  side: 'BUY' | 'SELL' | 'UNKNOWN'
  signalType: 'ENTRY' | 'EXIT' | 'UNKNOWN'
  decision: 'ACCEPTED' | 'REJECTED'
  rejectionReason: string | null
  stage: string | null
  conviction: number | null
}

interface SignalApiRow {
  id: number
  signal_id: string
  strategy_id: string
  symbol: string
  side: string
  signal_type: string
  decision: string
  rejection_reason?: string | null
  created_at: string
  metadata?: {
    stage?: string
    conviction_score?: number
    template_name?: string
  }
}

interface RecentSignalsPayload {
  signals: SignalApiRow[]
  summary: {
    total: number
    accepted: number
    rejected: number
    acceptance_rate: number
  }
}

const FILTER_OPTIONS = [
  { id: 'all' as const, label: 'All' },
  { id: 'entries' as const, label: 'Entries' },
  { id: 'exits' as const, label: 'Exits' },
  { id: 'rejections' as const, label: 'Rejected' },
]

type FilterId = (typeof FILTER_OPTIONS)[number]['id']

function rowFromApi(r: SignalApiRow): SignalRow {
  const meta = r.metadata || {}
  const rawType = (r.signal_type || '').toUpperCase()
  const signalType: SignalRow['signalType'] = rawType.includes('EXIT')
    ? 'EXIT'
    : rawType.includes('ENTRY') || rawType.includes('BUY') || rawType.includes('SELL')
      ? 'ENTRY'
      : 'UNKNOWN'
  const side: SignalRow['side'] =
    r.side === 'BUY' || r.side === 'SELL' ? r.side : 'UNKNOWN'

  return {
    id: r.signal_id || String(r.id),
    timestamp: r.created_at,
    symbol: r.symbol,
    strategyName: meta.template_name || r.strategy_id.slice(0, 8),
    side,
    signalType,
    decision: r.decision === 'ACCEPTED' ? 'ACCEPTED' : 'REJECTED',
    rejectionReason: r.rejection_reason ?? null,
    stage: meta.stage || null,
    conviction: typeof meta.conviction_score === 'number' ? meta.conviction_score : null,
  }
}

function rowFromWs(data: any): SignalRow | null {
  // `signal_generated` payload shape: { strategy_id, symbol, action, confidence, reasoning }
  if (!data || typeof data !== 'object') return null
  const action = String(data.action || '').toUpperCase()
  const side: SignalRow['side'] = action.includes('SELL') || action.includes('SHORT')
    ? 'SELL'
    : action.includes('BUY') || action.includes('LONG')
      ? 'BUY'
      : 'UNKNOWN'
  const signalType: SignalRow['signalType'] = action.includes('EXIT') ? 'EXIT' : 'ENTRY'
  return {
    id: `ws-${data.strategy_id || ''}-${data.symbol || ''}-${Date.now()}`,
    timestamp: new Date().toISOString(),
    symbol: String(data.symbol || ''),
    strategyName: data.strategy_name || data.strategy_id?.slice?.(0, 8) || null,
    side,
    signalType,
    decision: 'ACCEPTED',
    rejectionReason: null,
    stage: 'signal_emitted',
    conviction: typeof data.confidence === 'number' ? data.confidence * 100 : null,
  }
}

const MAX_BUFFER = 50

export function SignalFeed() {
  const mode = useTradingMode((s) => s.mode)
  const [filter, setFilter] = useState<FilterId>('all')
  const [buffer, setBuffer] = useState<SignalRow[]>([])
  const seededRef = useRef(false)

  // Seed via TanStack Query so mode change and mount re-fetch.
  const { data, isLoading } = useQuery<RecentSignalsPayload>({
    queryKey: ['recent-signals', mode],
    queryFn: () =>
      api.get<RecentSignalsPayload>('/signals/recent', { mode, limit: 50 }),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })

  useEffect(() => {
    if (!data?.signals) return
    const rows = data.signals.map(rowFromApi)
    // Full replace on fresh seed
    setBuffer(rows.slice(0, MAX_BUFFER))
    seededRef.current = true
  }, [data])

  // WebSocket prepend on each `signal_generated`.
  useEffect(() => {
    const off = wsManager.on('signal_generated', (raw) => {
      const row = rowFromWs(raw)
      if (!row) return
      setBuffer((prev) => {
        const next = [row, ...prev]
        return next.slice(0, MAX_BUFFER)
      })
    })
    return off
  }, [])

  const filtered = useMemo(() => {
    switch (filter) {
      case 'entries':
        return buffer.filter((r) => r.signalType === 'ENTRY')
      case 'exits':
        return buffer.filter((r) => r.signalType === 'EXIT')
      case 'rejections':
        return buffer.filter((r) => r.decision === 'REJECTED')
      case 'all':
      default:
        return buffer
    }
  }, [buffer, filter])

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-1 px-2 py-1 border-b border-[var(--border-subtle)] shrink-0">
        {FILTER_OPTIONS.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => setFilter(f.id)}
            className={cn(
              'h-5 px-1.5 rounded-[2px] text-[10px] font-medium uppercase tracking-wide transition-colors',
              filter === f.id
                ? 'bg-[var(--bg-active)] text-[var(--text-0)]'
                : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
            )}
          >
            {f.label}
          </button>
        ))}
        {data?.summary && (
          <span className="ml-auto mono text-[10px] text-[var(--text-3)]">
            {data.summary.acceptance_rate.toFixed(0)}% accepted
          </span>
        )}
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading && buffer.length === 0 && (
          <div className="flex flex-col gap-1 p-2">
            {Array.from({ length: 5 }).map((_, i) => (
              <Skeleton key={i} variant="table-row" />
            ))}
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <EmptyState
            icon={Zap}
            title="No signals yet"
            description="Signal decisions stream here as cycles fire. Watch this panel during market hours."
            className="py-6"
          />
        )}
        <ul className="divide-y divide-[var(--border-subtle)]">
          {filtered.map((row) => (
            <SignalRowItem key={row.id} row={row} />
          ))}
        </ul>
      </div>
    </div>
  )
}

function SignalRowItem({ row }: { row: SignalRow }) {
  const isReject = row.decision === 'REJECTED'
  const isBlocked = row.stage === 'gate_blocked'
  const dotColor = isBlocked
    ? 'var(--pnl-down)'
    : isReject
      ? 'var(--status-warning)'
      : 'var(--pnl-up)'

  const Icon = row.side === 'SELL' ? ArrowDownRight : ArrowUpRight
  const sideColor =
    row.side === 'SELL' ? 'var(--pnl-down)' : row.side === 'BUY' ? 'var(--pnl-up)' : 'var(--text-2)'

  return (
    <li
      className="flex items-start gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)] group"
      title={row.rejectionReason ?? row.stage ?? ''}
    >
      <span
        className="mt-[4px] inline-block h-1.5 w-1.5 rounded-full shrink-0"
        style={{ backgroundColor: dotColor }}
        aria-hidden
      />
      <Icon className="h-3 w-3 mt-[2px] shrink-0" style={{ color: sideColor }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline gap-1.5">
          <span className="mono text-[11px] font-semibold text-[var(--text-0)]">
            {row.symbol}
          </span>
          {row.conviction != null && (
            <span className="mono text-[10px] text-[var(--text-3)]">
              {row.conviction.toFixed(0)}
            </span>
          )}
          {isBlocked && (
            <ShieldBan className="h-3 w-3 text-[var(--pnl-down)]" />
          )}
        </div>
        <div className="text-[10px] text-[var(--text-2)] truncate">
          {row.strategyName || '—'}
          {row.rejectionReason ? ` · ${row.rejectionReason}` : ''}
        </div>
      </div>
      <span className="text-[10px] text-[var(--text-3)] mono shrink-0 pt-[2px]">
        {formatAge(row.timestamp)}
      </span>
    </li>
  )
}
