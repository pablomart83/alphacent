import { useState } from 'react'
import { toast } from 'sonner'
import {
  Activity,
  AlertCircle,
  ChevronRight,
  TrendingUp,
  X,
  Zap,
} from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { ConvictionBar } from '@/components/trading/ConvictionBar'
import { notifyError } from '@/lib/errors'
import { cn, formatCurrency, formatNumber, formatTimestamp } from '@/lib/utils'
import {
  useLiveStrategies,
  useRetireLiveStrategy,
  useStrategy,
  type LiveStrategyRow,
} from '../useStrategiesData'
import { useTradeJournal, type TradeJournalEntry } from '../../research/useResearchData'

/**
 * ActiveLiveTable — compact cards for each live-authorised pair.
 * Clicking a card calls onSelect to open the detail panel in the parent's
 * ResizablePanelLayout right pane (same pattern as GraduationCard).
 */
export function ActiveLiveTable({
  selectedId,
  onSelect,
}: {
  selectedId?: number | null
  onSelect?: (row: LiveStrategyRow | null) => void
}) {
  const query = useLiveStrategies()
  const retire = useRetireLiveStrategy()
  const [confirmRetire, setConfirmRetire] = useState<LiveStrategyRow | null>(null)

  const rows = query.data?.live_strategies ?? []

  const handleRetire = async () => {
    if (!confirmRetire) return
    try {
      await retire.mutateAsync({ liveId: confirmRetire.id })
      toast.success(
        `Retired ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}`,
      )
      if (selectedId === confirmRetire.id) onSelect?.(null)
      setConfirmRetire(null)
    } catch (err) {
      notifyError(err, 'retire live')
    }
  }

  return (
    <section className="flex flex-col gap-1.5 px-2 py-2 border-t border-[var(--border-subtle)]">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-[var(--pnl-up)]" />
          <SectionLabel className="mb-0">Active live authorisations</SectionLabel>
          <Badge variant="live" size="sm">{rows.length}</Badge>
        </div>
        <a
          href="/book/live?sub=divergence"
          className="text-[10px] text-[var(--accent-primary)] hover:underline"
        >
          Divergence heatmap →
        </a>
      </div>

      {/* Rows */}
      {query.isLoading ? (
        <Skeleton className="h-[44px]" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No live authorisations"
          description="Approve a candidate from the queue above."
          className="py-3"
        />
      ) : (
        <div className="space-y-1">
          {rows.map((row) => (
            <LiveStrategyRow
              key={row.id}
              row={row}
              isSelected={selectedId === row.id}
              onClick={() => onSelect?.(selectedId === row.id ? null : row)}
              onRetire={() => setConfirmRetire(row)}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmRetire}
        onOpenChange={(o) => !o && setConfirmRetire(null)}
        title="Retire live authorisation"
        description={
          confirmRetire
            ? `Retire ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}? Future signals stop firing live orders. Open live positions are NOT closed automatically.`
            : ''
        }
        confirmLabel="Retire"
        confirmVariant="destructive"
        isLoading={retire.isPending}
        onConfirm={handleRetire}
      />
    </section>
  )
}

/* ─────────────────────────── Compact row ─────────────────────────── */

function LiveStrategyRow({
  row,
  isSelected,
  onClick,
  onRetire,
}: {
  row: LiveStrategyRow
  isSelected: boolean
  onClick: () => void
  onRetire: () => void
}) {
  const divergence = row.divergence_pct
  const divergenceColor =
    divergence == null
      ? 'var(--text-3)'
      : divergence < 50
        ? 'var(--pnl-down)'
        : divergence < 80
          ? 'var(--status-warning)'
          : 'var(--pnl-up)'

  const livePnl = row.live_pnl ?? 0
  const liveTrades = row.live_trades ?? 0

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left rounded-[3px] border px-2.5 py-2 transition-colors group',
        isSelected
          ? 'border-[color-mix(in_oklab,var(--pnl-up)_50%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_8%,var(--bg-1))]'
          : 'border-[color-mix(in_oklab,var(--pnl-up)_20%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_3%,var(--bg-1))] hover:bg-[color-mix(in_oklab,var(--pnl-up)_6%,var(--bg-1))]',
      )}
    >
      <div className="flex items-center gap-2">
        {/* Pulse dot */}
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />

        {/* Name + symbol */}
        <span className="font-medium text-[11px] text-[var(--text-0)] truncate flex-1 min-w-0">
          {row.template_name ?? row.strategy_id}
        </span>
        <span className="mono text-[11px] font-bold text-[var(--pnl-up)] shrink-0">
          {row.symbol}
        </span>

        {/* Live badge */}
        <Badge variant="live" size="sm" className="gap-0.5 shrink-0">
          <Zap className="h-2.5 w-2.5" />
          LIVE
        </Badge>

        {/* Stats */}
        <div className="flex items-center gap-2 shrink-0 text-[10px] mono">
          {liveTrades > 0 ? (
            <span className={livePnl >= 0 ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]'}>
              {livePnl >= 0 ? '+' : ''}{formatCurrency(livePnl, { precision: 0 })}
            </span>
          ) : (
            <span className="text-[var(--text-3)]">waiting</span>
          )}
          {divergence != null && (
            <span className="flex items-center gap-0.5" style={{ color: divergenceColor }}>
              {divergence < 50 && <AlertCircle className="h-2.5 w-2.5" />}
              {divergence.toFixed(0)}%
            </span>
          )}
        </div>

        {/* Retire + chevron */}
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRetire() }}
          className="text-[10px] text-[var(--text-3)] hover:text-[var(--pnl-down)] transition-colors shrink-0 px-1"
        >
          Retire
        </button>
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 transition-transform',
            isSelected ? 'rotate-90 text-[var(--pnl-up)]' : 'text-[var(--text-3)] group-hover:text-[var(--text-1)]',
          )}
        />
      </div>
    </button>
  )
}

/* ─────────────────────────── Detail panel (side panel) ─────────────────────────── */

/**
 * LiveStrategyDetailPanel — renders in the right pane of ResizablePanelLayout.
 * Shows WF → Paper → Live phases with full historical detail.
 */
export function LiveStrategyDetailPanel({
  row,
  onClose,
  onRetire,
}: {
  row: LiveStrategyRow
  onClose: () => void
  onRetire: () => void
}) {
  const strategyQuery = useStrategy(row.strategy_id)
  const paperTradesQuery = useTradeJournal({
    strategyId: row.strategy_id,
    symbol: row.symbol,
    limit: 100,
  })

  const strategy = strategyQuery.data
  const wf = strategy?.walk_forward_results ?? null
  const paperTrades = paperTradesQuery.data?.trades ?? []
  const liveTrades = row.live_trades ?? 0
  const livePnl = row.live_pnl ?? 0

  const paperStats = paperTrades.reduce(
    (acc: { total: number; count: number; wins: number }, t) => {
      if (t.pnl != null) {
        acc.total += t.pnl
        acc.count++
        if (t.pnl > 0) acc.wins++
      }
      return acc
    },
    { total: 0, count: 0, wins: 0 },
  )
  const paperWinRate = paperStats.count > 0 ? (paperStats.wins / paperStats.count) * 100 : null

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-[var(--border-subtle)] shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="h-2 w-2 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />
            <span className="font-semibold text-[13px] text-[var(--text-0)] truncate">
              {row.template_name ?? row.strategy_id}
            </span>
            <span className="mono text-[12px] font-bold text-[var(--pnl-up)] shrink-0">
              {row.symbol}
            </span>
            <Badge variant="live" size="sm">LIVE</Badge>
          </div>
          <div className="text-[10px] text-[var(--text-3)] mono ml-4">
            Authorised {formatTimestamp(row.activated_at, 'short')}
            {' · '}${row.position_size?.toFixed(0) ?? '—'} virtual
            {' · '}SL {row.sl_pct != null ? `${(row.sl_pct * 100).toFixed(1)}%` : '—'}
            {' · '}TP {row.tp_pct != null ? `${(row.tp_pct * 100).toFixed(1)}%` : '—'}
            {' · '}C≥{row.conviction_min ?? '—'}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            className="text-[var(--pnl-down)] hover:text-[var(--pnl-down)] text-[11px] h-6"
            onClick={onRetire}
          >
            Retire
          </Button>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 min-h-0 overflow-auto px-3 py-3 space-y-4">

        {/* Phase 1: Walk-forward */}
        <PhaseSection label="Phase 1 — Walk-forward" color="var(--accent-primary)" badge="WF">
          {strategyQuery.isLoading ? (
            <Skeleton className="h-[52px]" />
          ) : wf ? (
            <div className="grid grid-cols-3 gap-1.5">
              <Metric label="Test Sharpe" value={wf.test_sharpe != null ? formatNumber(wf.test_sharpe, 2) : '—'} tone={wf.test_sharpe != null && wf.test_sharpe >= 1 ? 'up' : 'neutral'} />
              <Metric label="Train Sharpe" value={wf.train_sharpe != null ? formatNumber(wf.train_sharpe, 2) : '—'} />
              <Metric label="Test Win %" value={wf.test_win_rate != null ? `${(wf.test_win_rate * 100).toFixed(0)}%` : '—'} tone={wf.test_win_rate != null && wf.test_win_rate >= 0.55 ? 'up' : 'neutral'} />
              <Metric label="Test trades" value={wf.test_trades != null ? String(Math.round(wf.test_trades)) : '—'} />
              {wf.test_return != null && (
                <Metric label="Test return" value={`${(wf.test_return * 100).toFixed(1)}%`} tone={wf.test_return >= 0 ? 'up' : 'down'} />
              )}
              {wf.test_max_drawdown != null && (
                <Metric label="Test max DD" value={`${(Math.abs(wf.test_max_drawdown) * 100).toFixed(1)}%`} tone="down" />
              )}
            </div>
          ) : (
            <p className="text-[11px] text-[var(--text-3)]">Walk-forward data not available.</p>
          )}
        </PhaseSection>

        {/* Phase 2: Paper */}
        <PhaseSection label="Phase 2 — Paper (DEMO)" color="var(--accent-secondary)" badge="P">
          {paperTradesQuery.isLoading ? (
            <Skeleton className="h-[52px]" />
          ) : (
            <>
              <div className="grid grid-cols-3 gap-1.5 mb-3">
                <Metric label="Trades" value={String(row.current_paper_trades ?? paperStats.count)} />
                <Metric label="Win %" value={row.current_paper_win_rate != null ? `${(row.current_paper_win_rate * 100).toFixed(0)}%` : paperWinRate != null ? `${paperWinRate.toFixed(0)}%` : '—'} tone={(row.current_paper_win_rate ?? (paperWinRate != null ? paperWinRate / 100 : null)) != null && ((row.current_paper_win_rate ?? 0) >= 0.55 || (paperWinRate ?? 0) >= 55) ? 'up' : 'neutral'} />
                <Metric label="Total P&L" value={formatCurrency(row.current_paper_pnl ?? paperStats.total, { signed: true, precision: 0 })} tone={(row.current_paper_pnl ?? paperStats.total) >= 0 ? 'up' : 'down'} />
                <Metric label="Sharpe" value={row.current_paper_sharpe != null ? formatNumber(row.current_paper_sharpe, 2) : '—'} tone={row.current_paper_sharpe != null && row.current_paper_sharpe >= 1 ? 'up' : 'neutral'} />
              </div>
              {paperTrades.length > 0 && (
                <TradeTable trades={paperTrades.slice(0, 30)} label="Paper trades (last 30)" />
              )}
            </>
          )}
        </PhaseSection>

        {/* Phase 3: Live */}
        <PhaseSection label="Phase 3 — Live" color="var(--pnl-up)" badge="L">
          <div className="grid grid-cols-3 gap-1.5 mb-3">
            <Metric label="Trades" value={liveTrades > 0 ? String(liveTrades) : livePnl !== 0 || (row.open_position_count ?? 0) > 0 ? '1 open' : '—'} />
            <Metric
              label="P&L"
              value={
                liveTrades > 0 || livePnl !== 0
                  ? formatCurrency(livePnl, { signed: true, precision: 0 })
                  : (row.open_position_count ?? 0) > 0 && row.unrealized_pnl != null
                    ? `${formatCurrency(row.unrealized_pnl, { signed: true, precision: 0 })} unrlzd`
                    : 'Waiting'
              }
              tone={
                liveTrades > 0 || livePnl !== 0
                  ? (livePnl >= 0 ? 'up' : 'down')
                  : (row.open_position_count ?? 0) > 0 && row.unrealized_pnl != null
                    ? (row.unrealized_pnl >= 0 ? 'up' : 'down')
                    : 'neutral'
              }
            />
            <Metric label="Sharpe" value={row.live_sharpe != null ? formatNumber(row.live_sharpe, 2) : '—'} tone={row.live_sharpe != null && row.live_sharpe >= 1 ? 'up' : 'neutral'} />
            {row.divergence_pct != null && (
              <Metric
                label="Tracking"
                value={`${row.divergence_pct.toFixed(0)}%`}
                tone={row.divergence_pct >= 80 ? 'up' : row.divergence_pct >= 50 ? 'neutral' : 'down'}
              />
            )}
          </div>
          {liveTrades === 0 && livePnl === 0 && (row.open_position_count ?? 0) === 0 && (
            <div className="rounded-[3px] border border-[color-mix(in_oklab,var(--pnl-up)_20%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_4%,var(--bg-1))] px-2.5 py-2 text-[11px] text-[var(--text-2)]">
              <TrendingUp className="h-3.5 w-3.5 inline mr-1.5 text-[var(--pnl-up)]" />
              Gate open — next ENTER signal for{' '}
              <span className="mono font-medium text-[var(--pnl-up)]">{row.symbol}</span>{' '}
              with conviction ≥ {row.conviction_min ?? 74} fires a real order.
            </div>
          )}
        </PhaseSection>

        {/* Conviction gate */}
        {row.conviction_min != null && (
          <PhaseSection label="Live conviction gate" color="var(--accent-primary)" badge="C">
            <div className="space-y-1.5">
              <p className="text-[10px] text-[var(--text-3)]">
                Signals must score ≥ {row.conviction_min} to trigger a live fill.
              </p>
              <ConvictionBar score={row.conviction_min} size="default" showValue />
            </div>
          </PhaseSection>
        )}
      </div>
    </div>
  )
}

/* ─────────────────────────── Shared helpers ─────────────────────────── */

function PhaseSection({
  label,
  color,
  badge,
  children,
}: {
  label: string
  color: string
  badge: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span
          className="inline-flex items-center justify-center h-4 w-4 rounded-[2px] text-[8px] font-bold text-white shrink-0"
          style={{ backgroundColor: color }}
        >
          {badge}
        </span>
        <SectionLabel className="mb-0">{label}</SectionLabel>
      </div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2.5">
        {children}
      </div>
    </section>
  )
}

function Metric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[12px] font-semibold mt-0.5',
          tone === 'up' ? 'text-[var(--pnl-up)]' : tone === 'down' ? 'text-[var(--pnl-down)]' : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function TradeTable({ trades, label }: { trades: TradeJournalEntry[]; label: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">{label}</div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] max-h-[200px] overflow-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
              <th className="text-left px-2 py-1">Entry</th>
              <th className="text-right px-2 py-1">P&L</th>
              <th className="text-right px-2 py-1">P&L %</th>
              <th className="text-right px-2 py-1">Hold</th>
              <th className="text-left px-2 py-1">Exit</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                <td className="px-2 py-1 text-[var(--text-2)]">{formatTimestamp(t.entry_time, 'date')}</td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '')}>
                  {t.pnl != null ? formatCurrency(t.pnl, { signed: true, precision: 0 }) : '—'}
                </td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl_percent ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl_percent ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '')}>
                  {t.pnl_percent != null ? `${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                  {t.hold_time_hours != null ? (t.hold_time_hours < 48 ? `${t.hold_time_hours.toFixed(0)}h` : `${(t.hold_time_hours / 24).toFixed(1)}d`) : '—'}
                </td>
                <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[90px]">
                  {t.exit_reason?.replace(/_/g, ' ') ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
