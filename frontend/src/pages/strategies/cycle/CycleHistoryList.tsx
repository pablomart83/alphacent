import { useState } from 'react'
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Skeleton, EmptyState, Badge } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { ErrorState } from '@/components/primitives'
import { cn, formatTimestamp } from '@/lib/utils'
import {
  useAutonomousCycles,
  type CycleRunRow,
} from '../useStrategiesData'

/**
 * CycleHistoryList — last N cycles with duration and counts. Expand a row
 * to see a per-stage breakdown.
 */

interface CycleHistoryListProps {
  className?: string
  limit?: number
}

export function CycleHistoryList({ className, limit = 30 }: CycleHistoryListProps) {
  const query = useAutonomousCycles(limit)
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const rows = query.data?.data ?? []

  return (
    <section className={cn('flex flex-col min-h-0 p-2 gap-2', className)}>
      <div className="flex items-center gap-2 shrink-0">
        <SectionLabel>Cycle history</SectionLabel>
        <span className="ml-auto text-[10px] text-[var(--text-3)] mono">
          {rows.length} cycles
        </span>
      </div>

      {query.isError ? (
        <ErrorState
          title="Couldn't load cycle history"
          message={classifyError(query.error, 'cycle history').message}
          onRetry={() => query.refetch()}
        />
      ) : query.isLoading ? (
        <div className="flex flex-col gap-1 shrink-0">
          {Array.from({ length: 6 }).map((_, i) => (
            <Skeleton key={i} className="h-8 w-full" />
          ))}
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          title="No cycles yet"
          description="Trigger a cycle manually or wait for the next scheduled run."
        />
      ) : (
        <div className="flex-1 min-h-0 overflow-y-auto rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
          <ul className="divide-y divide-[var(--border-subtle)]">
            {rows.map((row) => (
              <CycleRow
                key={row.cycle_id}
                row={row}
                expanded={expandedId === row.cycle_id}
                onToggle={() =>
                  setExpandedId((cur) => (cur === row.cycle_id ? null : row.cycle_id))
                }
              />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}

function CycleRow({
  row,
  expanded,
  onToggle,
}: {
  row: CycleRunRow
  expanded: boolean
  onToggle: () => void
}) {
  const status = row.status?.toLowerCase() ?? 'unknown'
  const { StatusIcon, statusColor, statusVariant } = statusVisuals(status)

  return (
    <li>
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)] transition-colors text-left"
      >
        {expanded ? (
          <ChevronDown className="h-3 w-3 text-[var(--text-3)] shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 text-[var(--text-3)] shrink-0" />
        )}
        <StatusIcon
          className={cn(
            'h-3 w-3 shrink-0',
            statusColor,
            status === 'running' && 'animate-spin',
          )}
        />
        <div className="flex-1 min-w-0 grid grid-cols-[1fr_auto_auto] gap-2 items-baseline">
          <span className="text-[11px] text-[var(--text-0)] truncate">
            {formatTimestamp(row.started_at, 'short')}
          </span>
          <span className="mono text-[10px] text-[var(--text-3)]" title={row.cycle_id}>
            {row.cycle_id.slice(-8)}
          </span>
          <span className="mono text-[10px] text-[var(--text-2)]">
            {formatDuration(row.duration_seconds)}
          </span>
        </div>
        <div className="hidden md:flex items-center gap-2 text-[10px] text-[var(--text-3)] shrink-0">
          <CountCell label="P" value={row.proposals_generated} />
          <CountCell label="B" value={row.backtested} />
          <CountCell label="A" value={row.activated} />
          <CountCell label="S" value={row.signals_generated} />
        </div>
        <Badge variant={statusVariant} size="sm" className="shrink-0 capitalize">
          {status}
        </Badge>
      </button>

      {expanded && <CycleDetail row={row} />}
    </li>
  )
}

function CycleDetail({ row }: { row: CycleRunRow }) {
  return (
    <div className="border-t border-[var(--border-subtle)] bg-[var(--bg-0)] px-3 py-2">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-x-3 gap-y-1 text-[10px] mb-2">
        <DetailPair label="Cleaned" value={row.strategies_cleaned} />
        <DetailPair label="Retired" value={row.strategies_retired} />
        <DetailPair label="Trades analysed" value={row.trades_analyzed} />
        <DetailPair label="Template tweaks" value={row.template_adjustments} />
        <DetailPair label="Proposals" value={row.proposals_generated} />
        <DetailPair label="  Pre-WF" value={row.proposals_pre_wf} />
        <DetailPair label="  Alpha edge" value={row.proposals_alpha_edge} />
        <DetailPair label="  Template" value={row.proposals_template} />
        <DetailPair label="Symbols checked" value={row.symbols_checked} />
        <DetailPair label="  Passed" value={row.symbols_passed} />
        <DetailPair label="  Failed" value={row.symbols_failed} />
        <DetailPair label="Backtested" value={row.backtested} />
        <DetailPair label="  WF passed" value={row.backtest_passed} />
        <DetailPair label="  WF failed" value={row.backtest_failed} />
        <DetailPair
          label="Avg Sharpe"
          value={row.avg_sharpe != null ? row.avg_sharpe.toFixed(2) : '—'}
        />
        <DetailPair
          label="Avg WR"
          value={row.avg_win_rate != null ? `${(row.avg_win_rate * 100).toFixed(0)}%` : '—'}
        />
        <DetailPair label="Activated" value={row.activated} />
        <DetailPair label="Promoted → PAPER" value={row.promoted_to_paper} />
        <DetailPair label="Signals generated" value={row.signals_generated} />
        <DetailPair label="Signals passed" value={row.signals_passed} />
        <DetailPair label="Orders submitted" value={row.orders_submitted} />
        <DetailPair label="Orders filled" value={row.orders_filled} />
        <DetailPair label="Orders pending" value={row.orders_pending} />
        <DetailPair label="Orders rejected" value={row.orders_rejected} />
      </div>

      {Array.isArray(row.errors) && row.errors.length > 0 && (
        <div className="rounded-[2px] bg-[color-mix(in_oklab,var(--pnl-down)_10%,transparent)] border border-[var(--pnl-down)]/30 px-2 py-1 mb-1">
          <div className="text-[10px] uppercase tracking-wide text-[var(--pnl-down)] font-medium mb-1">
            Errors ({row.errors.length})
          </div>
          <ul className="space-y-0.5 text-[10px] text-[var(--text-1)]">
            {row.errors.slice(0, 5).map((err, i) => (
              <li key={i} className="truncate" title={String(err)}>
                {typeof err === 'string' ? err : JSON.stringify(err)}
              </li>
            ))}
            {row.errors.length > 5 && (
              <li className="text-[var(--text-3)]">… and {row.errors.length - 5} more</li>
            )}
          </ul>
        </div>
      )}
    </div>
  )
}

function CountCell({ label, value }: { label: string; value: number }) {
  return (
    <span title={label} className="mono">
      <span className="text-[var(--text-3)]">{label}</span>
      <span className="text-[var(--text-1)] ml-0.5">{value}</span>
    </span>
  )
}

function DetailPair({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline gap-1.5 min-w-0">
      <span className="text-[var(--text-3)] uppercase tracking-wide truncate">{label}</span>
      <span className="mono text-[var(--text-1)] ml-auto">{value}</span>
    </div>
  )
}

function statusVisuals(status: string): {
  StatusIcon: React.ComponentType<{ className?: string }>
  statusColor: string
  statusVariant: 'success' | 'warning' | 'error' | 'muted' | 'info'
} {
  switch (status) {
    case 'completed':
      return {
        StatusIcon: CheckCircle2,
        statusColor: 'text-[var(--pnl-up)]',
        statusVariant: 'success',
      }
    case 'running':
      return {
        StatusIcon: Loader2,
        statusColor: 'text-[var(--accent-primary)]',
        statusVariant: 'info',
      }
    case 'error':
    case 'failed':
      return {
        StatusIcon: AlertTriangle,
        statusColor: 'text-[var(--pnl-down)]',
        statusVariant: 'error',
      }
    default:
      return {
        StatusIcon: CheckCircle2,
        statusColor: 'text-[var(--text-3)]',
        statusVariant: 'muted',
      }
  }
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  if (m === 0) return `${s}s`
  if (s === 0) return `${m}m`
  return `${m}m ${s}s`
}
