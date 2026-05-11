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
  Dialog,
  DialogContent,
  DialogTitle,
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
 * ActiveLiveTable — prominent cards for each live-authorised (template × symbol) pair.
 *
 * Each card shows the three-phase pipeline at a glance:
 *   WF → Paper → Live
 *
 * Clicking a card opens a deep-dive drawer with full historical detail.
 */
export function ActiveLiveTable() {
  const query = useLiveStrategies()
  const retire = useRetireLiveStrategy()

  const [confirmRetire, setConfirmRetire] = useState<LiveStrategyRow | null>(null)
  const [selectedRow, setSelectedRow] = useState<LiveStrategyRow | null>(null)

  const rows = query.data?.live_strategies ?? []

  const handleRetire = async () => {
    if (!confirmRetire) return
    try {
      await retire.mutateAsync({ liveId: confirmRetire.id })
      toast.success(
        `Retired ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}`,
      )
      setConfirmRetire(null)
      if (selectedRow?.id === confirmRetire.id) setSelectedRow(null)
    } catch (err) {
      notifyError(err, 'retire live')
    }
  }

  return (
    <section className="flex flex-col gap-2 px-2 py-2 border-t border-[var(--border-subtle)]">
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

      {/* Cards */}
      {query.isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-[88px]" />
        </div>
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No live authorisations"
          description="Approve a candidate from the queue above to authorise the first (template, symbol) pair."
          className="py-4"
        />
      ) : (
        <div className="space-y-2">
          {rows.map((row) => (
            <LiveStrategyCard
              key={row.id}
              row={row}
              onClick={() => setSelectedRow(row)}
              onRetire={() => setConfirmRetire(row)}
            />
          ))}
        </div>
      )}

      {/* Deep-dive drawer */}
      {selectedRow && (
        <LiveStrategyDrawer
          row={selectedRow}
          onClose={() => setSelectedRow(null)}
          onRetire={() => {
            setConfirmRetire(selectedRow)
            setSelectedRow(null)
          }}
        />
      )}

      <ConfirmDialog
        open={!!confirmRetire}
        onOpenChange={(o) => !o && setConfirmRetire(null)}
        title="Retire live authorisation"
        description={
          confirmRetire
            ? `Retire ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}? Future signals stop firing live orders. Open live positions are NOT closed automatically — use Book → Live to close them.`
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

/* ─────────────────────────── Card ─────────────────────────── */

function LiveStrategyCard({
  row,
  onClick,
  onRetire: _onRetire,
}: {
  row: LiveStrategyRow
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
        'w-full text-left rounded-[4px] border p-3 transition-colors group',
        'border-[color-mix(in_oklab,var(--pnl-up)_25%,var(--border-subtle))]',
        'bg-[color-mix(in_oklab,var(--pnl-up)_3%,var(--bg-1))]',
        'hover:bg-[color-mix(in_oklab,var(--pnl-up)_6%,var(--bg-1))]',
        'hover:border-[color-mix(in_oklab,var(--pnl-up)_40%,var(--border-subtle))]',
      )}
    >
      {/* Top row: name + symbol + live badge + chevron */}
      <div className="flex items-start justify-between gap-2 mb-2.5">
        <div className="flex items-center gap-2 min-w-0">
          <span className="h-2 w-2 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />
          <span className="font-semibold text-[12px] text-[var(--text-0)] truncate">
            {row.template_name ?? row.strategy_id}
          </span>
          <span className="mono text-[11px] font-bold text-[var(--pnl-up)] shrink-0">
            {row.symbol}
          </span>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          <Badge variant="live" size="sm" className="gap-1">
            <Zap className="h-2.5 w-2.5" />
            LIVE
          </Badge>
          <ChevronRight className="h-3.5 w-3.5 text-[var(--text-3)] group-hover:text-[var(--text-1)] transition-colors" />
        </div>
      </div>

      {/* Three-phase pipeline */}
      <div className="grid grid-cols-3 gap-2 mb-2.5">
        <PhaseBlock
          label="Walk-forward"
          icon="WF"
          iconColor="var(--accent-primary)"
          metrics={[
            {
              label: 'Test Sharpe',
              value: row.current_paper_sharpe != null
                ? formatNumber(row.current_paper_sharpe, 2)
                : '—',
            },
          ]}
        />
        <PhaseBlock
          label="Paper"
          icon="P"
          iconColor="var(--accent-secondary)"
          metrics={[
            {
              label: 'Sharpe',
              value: row.current_paper_sharpe != null
                ? formatNumber(row.current_paper_sharpe, 2)
                : '—',
            },
            {
              label: 'P&L',
              value: row.current_paper_pnl != null
                ? formatCurrency(row.current_paper_pnl, { signed: true, precision: 0 })
                : '—',
              color: row.current_paper_pnl != null
                ? row.current_paper_pnl >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'
                : undefined,
            },
          ]}
        />
        <PhaseBlock
          label="Live"
          icon="L"
          iconColor="var(--pnl-up)"
          metrics={[
            {
              label: 'Trades',
              value: liveTrades > 0 ? String(liveTrades) : '—',
            },
            {
              label: 'P&L',
              value: liveTrades > 0
                ? formatCurrency(livePnl, { signed: true, precision: 0 })
                : 'Waiting',
              color: liveTrades > 0
                ? livePnl >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'
                : 'var(--text-3)',
            },
          ]}
        />
      </div>

      {/* Bottom row: config + divergence + activated */}
      <div className="flex items-center justify-between gap-2 text-[10px]">
        <div className="flex items-center gap-2 mono text-[var(--text-3)]">
          <span>${row.position_size?.toFixed(0) ?? '—'}</span>
          <span>·</span>
          <span>SL {row.sl_pct != null ? `${(row.sl_pct * 100).toFixed(1)}%` : '—'}</span>
          <span>·</span>
          <span>TP {row.tp_pct != null ? `${(row.tp_pct * 100).toFixed(1)}%` : '—'}</span>
          <span>·</span>
          <span>C≥{row.conviction_min ?? '—'}</span>
        </div>
        <div className="flex items-center gap-2">
          {divergence != null && (
            <span className="flex items-center gap-1">
              {divergence < 50 && <AlertCircle className="h-3 w-3" style={{ color: divergenceColor }} />}
              <span className="mono" style={{ color: divergenceColor }}>
                {divergence.toFixed(0)}% track
              </span>
            </span>
          )}
          <span className="text-[var(--text-3)]">
            {formatTimestamp(row.activated_at, 'short')}
          </span>
        </div>
      </div>
    </button>
  )
}

function PhaseBlock({
  label,
  icon,
  iconColor,
  metrics,
}: {
  label: string
  icon: string
  iconColor: string
  metrics: Array<{ label: string; value: string; color?: string }>
}) {
  return (
    <div className="rounded-[3px] bg-[var(--bg-0)] border border-[var(--border-subtle)] px-2 py-1.5 space-y-1">
      <div className="flex items-center gap-1">
        <span
          className="inline-flex items-center justify-center h-3.5 w-3.5 rounded-[2px] text-[8px] font-bold text-white shrink-0"
          style={{ backgroundColor: iconColor }}
        >
          {icon}
        </span>
        <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] font-medium">
          {label}
        </span>
      </div>
      {metrics.map((m) => (
        <div key={m.label}>
          <div className="text-[8px] uppercase tracking-wider text-[var(--text-3)]">{m.label}</div>
          <div
            className="mono tabular-nums text-[11px] font-semibold"
            style={{ color: m.color ?? 'var(--text-0)' }}
          >
            {m.value}
          </div>
        </div>
      ))}
    </div>
  )
}

/* ─────────────────────────── Deep-dive drawer ─────────────────────────── */

function LiveStrategyDrawer({
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

  // Aggregate paper stats from trade journal
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
    <Dialog open onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg" className="max-h-[85vh] overflow-auto">
        {/* Header */}
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-0.5">
              <span className="h-2 w-2 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />
              <DialogTitle className="text-[14px] font-semibold truncate">
                {row.template_name ?? row.strategy_id}
              </DialogTitle>
              <span className="mono text-[12px] font-bold text-[var(--pnl-up)]">
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
          <div className="flex items-center gap-1.5 shrink-0">
            <Button
              size="sm"
              variant="ghost"
              className="text-[var(--pnl-down)] hover:text-[var(--pnl-down)]"
              onClick={onRetire}
            >
              Retire
            </Button>
            <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>

        <div className="space-y-4 mt-3">
          {/* Phase 1: Walk-forward */}
          <PhaseSection
            label="Phase 1 — Walk-forward validation"
            color="var(--accent-primary)"
            badge="WF"
          >
            {strategyQuery.isLoading ? (
              <Skeleton className="h-[60px]" />
            ) : wf ? (
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                <DrawerMetric
                  label="Test Sharpe"
                  value={wf.test_sharpe != null ? formatNumber(wf.test_sharpe, 2) : '—'}
                  tone={wf.test_sharpe != null && wf.test_sharpe >= 1 ? 'up' : 'neutral'}
                />
                <DrawerMetric
                  label="Train Sharpe"
                  value={wf.train_sharpe != null ? formatNumber(wf.train_sharpe, 2) : '—'}
                />
                <DrawerMetric
                  label="Test Win rate"
                  value={wf.test_win_rate != null ? `${(wf.test_win_rate * 100).toFixed(0)}%` : '—'}
                  tone={wf.test_win_rate != null && wf.test_win_rate >= 0.55 ? 'up' : 'neutral'}
                />
                <DrawerMetric
                  label="Test trades"
                  value={wf.test_trades != null ? String(Math.round(wf.test_trades)) : '—'}
                />
                {wf.test_return != null && (
                  <DrawerMetric
                    label="Test return"
                    value={`${(wf.test_return * 100).toFixed(1)}%`}
                    tone={wf.test_return >= 0 ? 'up' : 'down'}
                  />
                )}
                {wf.test_max_drawdown != null && (
                  <DrawerMetric
                    label="Test max DD"
                    value={`${(Math.abs(wf.test_max_drawdown) * 100).toFixed(1)}%`}
                    tone="down"
                  />
                )}
              </div>
            ) : (
              <div className="text-[11px] text-[var(--text-3)]">
                Walk-forward data not available for this strategy version.
              </div>
            )}
          </PhaseSection>

          {/* Phase 2: Paper trading */}
          <PhaseSection
            label="Phase 2 — Paper trading (DEMO)"
            color="var(--accent-secondary)"
            badge="P"
          >
            {paperTradesQuery.isLoading ? (
              <Skeleton className="h-[60px]" />
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
                  <DrawerMetric
                    label="Total trades"
                    value={String(paperStats.count)}
                  />
                  <DrawerMetric
                    label="Win rate"
                    value={paperWinRate != null ? `${paperWinRate.toFixed(0)}%` : '—'}
                    tone={paperWinRate != null && paperWinRate >= 55 ? 'up' : 'neutral'}
                  />
                  <DrawerMetric
                    label="Total P&L"
                    value={formatCurrency(paperStats.total, { signed: true, precision: 0 })}
                    tone={paperStats.total >= 0 ? 'up' : 'down'}
                  />
                  <DrawerMetric
                    label="Sharpe"
                    value={row.current_paper_sharpe != null
                      ? formatNumber(row.current_paper_sharpe, 2)
                      : '—'}
                    tone={row.current_paper_sharpe != null && row.current_paper_sharpe >= 1 ? 'up' : 'neutral'}
                  />
                </div>
                {paperTrades.length > 0 && (
                  <TradeTable trades={paperTrades.slice(0, 20)} label="Last 20 paper trades" />
                )}
              </>
            )}
          </PhaseSection>

          {/* Phase 3: Live */}
          <PhaseSection
            label="Phase 3 — Live trading"
            color="var(--pnl-up)"
            badge="L"
          >
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 mb-3">
              <DrawerMetric
                label="Live trades"
                value={liveTrades > 0 ? String(liveTrades) : '—'}
              />
              <DrawerMetric
                label="Live P&L"
                value={liveTrades > 0
                  ? formatCurrency(livePnl, { signed: true, precision: 0 })
                  : 'Waiting for first fill'}
                tone={liveTrades > 0 ? (livePnl >= 0 ? 'up' : 'down') : 'neutral'}
              />
              <DrawerMetric
                label="Live Sharpe"
                value={row.live_sharpe != null ? formatNumber(row.live_sharpe, 2) : '—'}
                tone={row.live_sharpe != null && row.live_sharpe >= 1 ? 'up' : 'neutral'}
              />
              {row.divergence_pct != null && (
                <DrawerMetric
                  label="Tracking (live/paper)"
                  value={`${row.divergence_pct.toFixed(0)}%`}
                  tone={row.divergence_pct >= 80 ? 'up' : row.divergence_pct >= 50 ? 'neutral' : 'down'}
                />
              )}
            </div>
            {liveTrades === 0 && (
              <div className="rounded-[3px] border border-[color-mix(in_oklab,var(--pnl-up)_20%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_4%,var(--bg-1))] px-3 py-2 text-[11px] text-[var(--text-2)]">
                <TrendingUp className="h-3.5 w-3.5 inline mr-1.5 text-[var(--pnl-up)]" />
                Live gate is open. The next ENTER signal for{' '}
                <span className="mono font-medium text-[var(--pnl-up)]">{row.symbol}</span>{' '}
                with conviction ≥ {row.conviction_min ?? 74} will fire a real order on eToro
                Agent Portfolio.
              </div>
            )}
          </PhaseSection>

          {/* Conviction bar */}
          {row.conviction_min != null && (
            <PhaseSection label="Live conviction gate" color="var(--accent-primary)" badge="C">
              <div className="space-y-1.5">
                <div className="text-[10px] text-[var(--text-3)]">
                  Signals must score ≥ {row.conviction_min} to trigger a live fill.
                </div>
                <ConvictionBar score={row.conviction_min} size="default" showValue />
              </div>
            </PhaseSection>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/* ─────────────────────────── Helpers ─────────────────────────── */

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
    <section className="space-y-2">
      <div className="flex items-center gap-2">
        <span
          className="inline-flex items-center justify-center h-4 w-4 rounded-[2px] text-[9px] font-bold text-white shrink-0"
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

function DrawerMetric({
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
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function TradeTable({
  trades,
  label,
}: {
  trades: TradeJournalEntry[]
  label: string
}) {
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
                <td className="px-2 py-1 text-[var(--text-2)]">
                  {formatTimestamp(t.entry_time, 'date')}
                </td>
                <td className={cn(
                  'px-2 py-1 text-right mono tabular-nums',
                  (t.pnl ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '',
                )}>
                  {t.pnl != null
                    ? formatCurrency(t.pnl, { signed: true, precision: 0 })
                    : '—'}
                </td>
                <td className={cn(
                  'px-2 py-1 text-right mono tabular-nums',
                  (t.pnl_percent ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl_percent ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '',
                )}>
                  {t.pnl_percent != null
                    ? `${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent.toFixed(1)}%`
                    : '—'}
                </td>
                <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                  {t.hold_time_hours != null
                    ? t.hold_time_hours < 48
                      ? `${t.hold_time_hours.toFixed(0)}h`
                      : `${(t.hold_time_hours / 24).toFixed(1)}d`
                    : '—'}
                </td>
                <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[100px]">
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
