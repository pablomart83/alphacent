import { X } from 'lucide-react'
import { Button, Dialog, DialogContent, DialogTitle } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber, formatTimestamp } from '@/lib/utils'
import { useStrategy } from '@/pages/strategies/useStrategiesData'
import { useTradeJournal } from '../useResearchData'

/**
 * StrategyDeepDiveDrawer — per-strategy tear sheet opened from the
 * Attribution table. Shows: key metrics, trade journal summary,
 * regime breakdown, conviction score, and a link to the full strategy
 * detail in the Library.
 */

interface StrategyDeepDiveDrawerProps {
  strategyId: string | null
  onClose: () => void
}

export function StrategyDeepDiveDrawer({
  strategyId,
  onClose,
}: StrategyDeepDiveDrawerProps) {
  const strategy = useStrategy(strategyId)
  const journal = useTradeJournal({ strategyId: strategyId ?? undefined, limit: 50 })

  const s = strategy.data
  const trades = journal.data?.trades ?? []

  const winTrades = trades.filter((t) => (t.pnl ?? 0) > 0)
  const lossTrades = trades.filter((t) => (t.pnl ?? 0) < 0)
  const totalPnl = trades.reduce((a, t) => a + (t.pnl ?? 0), 0)
  const avgHold =
    trades.length > 0
      ? trades.reduce((a, t) => a + (t.hold_time_hours ?? 0), 0) / trades.length
      : 0

  return (
    <Dialog open={strategyId != null} onOpenChange={(v) => !v && onClose()}>
      <DialogContent size="lg" className="max-h-[80vh] overflow-auto">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <DialogTitle className="text-[14px] font-semibold truncate">
              {strategy.isLoading ? 'Loading…' : s?.name ?? strategyId}
            </DialogTitle>
            {s && (
              <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[var(--text-3)]">
                <span className="mono">{s.status}</span>
                {s.template_name && <span>· {s.template_name}</span>}
                {s.market_regime && <span>· {s.market_regime.replace(/_/g, ' ')}</span>}
              </div>
            )}
          </div>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
            <X className="h-3.5 w-3.5" />
          </Button>
        </div>

        {s && (
          <div className="space-y-4 mt-2">
            {/* Key metrics */}
            <section className="space-y-1.5">
              <SectionLabel>Performance metrics</SectionLabel>
              <div className="grid grid-cols-4 gap-2">
                <MetricTile label="Sharpe" value={formatNumber(s.performance_metrics?.sharpe_ratio ?? 0, 2)} tone={s.performance_metrics?.sharpe_ratio != null && s.performance_metrics.sharpe_ratio >= 1 ? 'up' : 'neutral'} />
                <MetricTile label="Win rate" value={`${formatNumber(s.performance_metrics?.win_rate ?? 0, 1)}%`} tone={s.performance_metrics?.win_rate != null && s.performance_metrics.win_rate >= 55 ? 'up' : 'neutral'} />
                <MetricTile label="Trades" value={formatNumber(s.performance_metrics?.total_trades ?? 0, 0)} />
                <MetricTile label="Max DD" value={`−${formatNumber(s.performance_metrics?.max_drawdown ?? 0, 1)}%`} tone="down" />
              </div>
            </section>

            {/* Trade journal summary */}
            {trades.length > 0 && (
              <section className="space-y-1.5">
                <SectionLabel>Trade journal · last {trades.length} trades</SectionLabel>
                <div className="grid grid-cols-4 gap-2">
                  <MetricTile label="Total P&L" value={`${totalPnl >= 0 ? '+' : ''}${formatNumber(totalPnl, 0)}`} tone={totalPnl > 0 ? 'up' : totalPnl < 0 ? 'down' : 'neutral'} />
                  <MetricTile label="Wins" value={formatNumber(winTrades.length, 0)} tone="up" />
                  <MetricTile label="Losses" value={formatNumber(lossTrades.length, 0)} tone="down" />
                  <MetricTile label="Avg hold" value={avgHold < 48 ? `${avgHold.toFixed(1)}h` : `${(avgHold / 24).toFixed(1)}d`} />
                </div>
                <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] max-h-[200px] overflow-auto">
                  <table className="w-full text-[10px]">
                    <thead>
                      <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
                        <th className="text-left px-2 py-1">Symbol</th>
                        <th className="text-left px-2 py-1">Entry</th>
                        <th className="text-right px-2 py-1">P&L</th>
                        <th className="text-right px-2 py-1">Hold</th>
                        <th className="text-left px-2 py-1">Exit reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.map((t) => (
                        <tr key={t.id} className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                          <td className="px-2 py-1 mono font-medium">{t.symbol}</td>
                          <td className="px-2 py-1 text-[var(--text-2)]">{formatTimestamp(t.entry_time, 'date')}</td>
                          <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '')}>
                            {t.pnl != null ? `${t.pnl >= 0 ? '+' : ''}${formatNumber(t.pnl, 0)}` : '—'}
                          </td>
                          <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                            {t.hold_time_hours != null ? (t.hold_time_hours < 48 ? `${t.hold_time_hours.toFixed(1)}h` : `${(t.hold_time_hours / 24).toFixed(1)}d`) : '—'}
                          </td>
                          <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[120px]">
                            {t.exit_reason?.replace(/_/g, ' ') ?? '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </section>
            )}

            {/* Conviction + metadata */}
            {s.metadata && (
              <section className="space-y-1.5">
                <SectionLabel>Signal metadata</SectionLabel>
                <div className="grid grid-cols-3 gap-2">
                  {s.metadata.conviction_score != null && (
                    <MetricTile label="Conviction" value={formatNumber(Number(s.metadata.conviction_score), 0)} tone={Number(s.metadata.conviction_score) >= 74 ? 'up' : 'neutral'} />
                  )}
                  {s.metadata.interval && (
                    <MetricTile label="Interval" value={String(s.metadata.interval)} />
                  )}
                  {s.metadata.direction && (
                    <MetricTile label="Direction" value={String(s.metadata.direction).toUpperCase()} />
                  )}
                </div>
              </section>
            )}
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function MetricTile({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[13px] font-semibold mt-0.5',
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
