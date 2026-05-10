import { X } from 'lucide-react'
import {
  Badge,
  Button,
  EmptyState,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatCurrency, formatNumber, formatTimestamp } from '@/lib/utils'
import type { SymbolStatsRow } from '../useStrategiesData'

interface SymbolDetailDrawerProps {
  symbol: SymbolStatsRow | null
  onClose: () => void
}

/**
 * SymbolDetailDrawer — surfaces all available context per symbol:
 * proposal / activation / trade counts, avg perf, best+worst template,
 * last-seen signal & trade times.
 *
 * The backend /strategies/symbols endpoint doesn't expose a historical
 * timeseries today; we surface what we have and flag the missing pieces
 * rather than invent numbers.
 */
export function SymbolDetailDrawer({ symbol, onClose }: SymbolDetailDrawerProps) {
  if (!symbol) {
    return (
      <div className="flex h-full items-center justify-center bg-[var(--bg-0)]">
        <EmptyState
          title="Select a symbol"
          description="Click a row to inspect proposal + trade history."
        />
      </div>
    )
  }

  const funnelConversion =
    symbol.proposed_count > 0
      ? (symbol.approved_count / symbol.proposed_count) * 100
      : null

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <header className="shrink-0 flex items-start justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3 className="mono text-[16px] font-semibold text-[var(--text-0)]">
              {symbol.symbol}
            </h3>
            <Badge variant="muted" size="sm">
              {symbol.asset_class}
            </Badge>
            {symbol.sector && symbol.sector !== 'unknown' && (
              <Badge variant="info" size="sm">
                {symbol.sector}
              </Badge>
            )}
          </div>
          <p className="text-[10px] text-[var(--text-3)] mt-0.5">
            {symbol.open_positions > 0
              ? `${symbol.open_positions} position${symbol.open_positions === 1 ? '' : 's'} open now`
              : 'No open positions'}
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
          <X className="h-3.5 w-3.5" />
        </Button>
      </header>

      <div className="flex-1 min-h-0 overflow-auto px-3 py-2 space-y-4">
        <section>
          <SectionLabel>Lifetime usage</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <StatTile label="Proposed" value={symbol.proposed_count} />
            <StatTile label="Approved" value={symbol.approved_count} />
            <StatTile label="Activated" value={symbol.activated_count} />
            <StatTile label="Traded" value={symbol.traded_count} />
            <StatTile
              label="Active strategies"
              value={symbol.active_strategies}
              emphasise={symbol.active_strategies > 0}
            />
            <StatTile
              label="Conversion"
              value={
                funnelConversion != null
                  ? `${funnelConversion.toFixed(0)}%`
                  : '—'
              }
            />
          </div>
        </section>

        <section>
          <SectionLabel>Performance (live trades)</SectionLabel>
          <div className="grid grid-cols-2 gap-2">
            <StatTile
              label="Live trades"
              value={symbol.total_trades_live}
            />
            <StatTile
              label="Avg Sharpe"
              value={
                symbol.avg_sharpe != null ? symbol.avg_sharpe.toFixed(2) : '—'
              }
            />
            <StatTile
              label="Win rate"
              value={
                symbol.avg_win_rate != null
                  ? `${(symbol.avg_win_rate * 100).toFixed(1)}%`
                  : '—'
              }
            />
            <StatTile
              label="Total P&L"
              value={
                symbol.total_pnl != null ? (
                  <PnLNumber
                    value={symbol.total_pnl}
                    format="currency"
                    precision={0}
                    size="sm"
                    showSign
                  />
                ) : (
                  '—'
                )
              }
            />
          </div>
        </section>

        <section>
          <SectionLabel>Best / worst template</SectionLabel>
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1 text-[10px]">
            {symbol.best_template ? (
              <div className="flex items-start gap-2">
                <span className="text-[var(--pnl-up)] shrink-0 w-16">Best</span>
                <span
                  className="text-[var(--text-1)] truncate"
                  title={symbol.best_template}
                >
                  {symbol.best_template}
                </span>
              </div>
            ) : (
              <div className="text-[var(--text-3)]">No best template yet</div>
            )}
            {symbol.worst_template && symbol.worst_template !== symbol.best_template ? (
              <div className="flex items-start gap-2">
                <span className="text-[var(--pnl-down)] shrink-0 w-16">Worst</span>
                <span
                  className="text-[var(--text-1)] truncate"
                  title={symbol.worst_template}
                >
                  {symbol.worst_template}
                </span>
              </div>
            ) : null}
          </div>
        </section>

        <section>
          <SectionLabel>Activity</SectionLabel>
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1 text-[10px]">
            <ActivityRow
              label="Last signal"
              value={formatTimestamp(symbol.last_signal, 'long') || '—'}
            />
            <ActivityRow
              label="Last trade"
              value={formatTimestamp(symbol.last_trade, 'long') || '—'}
            />
          </div>
        </section>

        <section className="text-[10px] text-[var(--text-3)] leading-relaxed">
          Historical proposal + trade timelines and regime-sensitivity plots require the
          analytics service to expose per-symbol series — not in today's backend. Aggregate
          lifetime stats are sourced from <span className="mono">strategy_proposals</span>{' '}
          and <span className="mono">trade_journal</span>.
        </section>
      </div>
    </div>
  )
}

function StatTile({
  label,
  value,
  emphasise,
}: {
  label: string
  value: React.ReactNode
  emphasise?: boolean
}) {
  return (
    <div
      className={cn(
        'rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2',
        emphasise && 'border-[var(--accent-primary)] bg-[color-mix(in_oklab,var(--accent-primary)_6%,var(--bg-1))]',
      )}
    >
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div className="mono tabular-nums text-[14px] text-[var(--text-0)] mt-0.5">
        {typeof value === 'number' ? formatNumber(value, 0) : value}
      </div>
    </div>
  )
}

function ActivityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[var(--text-3)] uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span className="mono text-[var(--text-1)] truncate" title={value}>
        {value}
      </span>
    </div>
  )
}

/* Silence unused import. */
export const __fmtCurrency = formatCurrency
