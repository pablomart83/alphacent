import { TrendingUp } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { cn, formatAge, formatNumber } from '@/lib/utils'
import {
  useApproachingGraduation,
  type ApproachingGraduationRow,
} from '../useStrategiesData'

/**
 * ApproachingGraduationPanel — top candidates building toward graduation.
 *
 * Data source: GET /strategies/approaching-graduation
 *
 * Why this endpoint exists (and why the old client-side approach was wrong):
 *
 *   1. Graduation is evaluated against trade_journal (closed trades with P&L),
 *      not performance_metrics.total_trades (which counts open positions too).
 *
 *   2. Every time the proposer creates a strategy it gets a new UUID. When a
 *      strategy retires and the same (template, symbol) pair is re-proposed,
 *      the new strategy_id starts from zero in the graduation gate's view.
 *      The backend endpoint groups by (template_name, symbol) across ALL
 *      strategy IDs so historical evidence accumulates correctly.
 *
 *   3. The graduation thresholds are: trades ≥ 20, win rate ≥ 45%, P&L > 0,
 *      and paper_sharpe ≥ 60% of WF sharpe. The composite score weights
 *      progress toward each gate so the closest candidates surface first.
 */

// Graduation thresholds — these are defaults; the backend returns per-row
// effective values (effective_win_rate_floor, effective_max_ratio) that
// account for strategy type and current market regime.
const MIN_TRADES = 8   // lowest per-interval threshold (1d strategies)
const MIN_WIN_RATE = 0.45  // lowest floor (trend-following strategies)
const MIN_QUAL_RATIO = 0.60
const MAX_QUAL_RATIO = 3.5  // highest regime-adjusted cap (trending_up_strong)

export function ApproachingGraduationPanel() {
  const query = useApproachingGraduation(5, 20)

  if (query.isLoading && !query.data) {
    return (
      <section className="space-y-1.5 px-2 pb-2">
        <SectionLabel>Approaching graduation</SectionLabel>
        <Skeleton className="h-[280px] w-full" />
      </section>
    )
  }

  const rows = query.data?.approaching ?? []

  if (!rows.length) {
    return (
      <section className="space-y-1.5 px-2 pb-2">
        <SectionLabel>Approaching graduation</SectionLabel>
        <EmptyState
          icon={TrendingUp}
          title="No candidates approaching graduation"
          description="Pairs appear here once they have ≥ 5 closed trades in the journal but haven't yet crossed all graduation thresholds."
          className="py-6"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5 px-2 pb-2">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            {rows.length} candidates · thresholds: {MIN_TRADES}+ trades · Sharpe {MIN_QUAL_RATIO}–{MAX_QUAL_RATIO}× WF · WR ≥ {MIN_WIN_RATE * 100}% · P&L {'>'} 0 · regime-adjusted
          </span>
        }
      >
        Approaching graduation
      </SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] divide-y divide-[var(--border-subtle)]">
        {rows.map((r) => (
          <ApproachingRow key={`${r.template_name}::${r.symbol}`} row={r} />
        ))}
      </div>
    </section>
  )
}

function ApproachingRow({ row }: { row: ApproachingGraduationRow }) {
  // Use per-row effective thresholds from backend (regime + strategy-type aware)
  // Fall back to module constants if backend doesn't return them yet.
  const effectiveWrFloor = (row as any).effective_win_rate_floor ?? MIN_WIN_RATE
  const effectiveMaxRatio = (row as any).effective_max_ratio ?? MAX_QUAL_RATIO

  const tradesPct = Math.min(100, (row.trades / MIN_TRADES) * 100)
  const wrPct = Math.min(100, row.win_rate * 100)
  const qualPct =
    row.qualification_ratio != null
      ? Math.min(100, (row.qualification_ratio / effectiveMaxRatio) * 100)
      : row.sharpe > 0
        ? Math.min(100, (row.sharpe / 1.0) * 100)
        : 0
  const pnlOk = row.total_pnl > 0
  const ratioMet =
    row.qualification_ratio != null
      ? row.qualification_ratio >= MIN_QUAL_RATIO && row.qualification_ratio <= effectiveMaxRatio
      : row.sharpe >= 1.0

  return (
    <div className="px-3 py-2 space-y-2">
      {/* Header row */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div
            className="text-[11px] font-medium text-[var(--text-0)] truncate"
            title={row.template_name}
          >
            {row.template_name}
          </div>
          <div className="flex items-center gap-2 mt-0.5 text-[10px] text-[var(--text-3)]">
            <span className="mono font-medium text-[var(--text-2)]">{row.symbol}</span>
            {row.strategy_versions > 1 && (
              <span title={`${row.strategy_versions} strategy versions contributed trades`}>
                {row.strategy_versions} versions
              </span>
            )}
            {row.last_trade && (
              <span>last trade {formatAge(row.last_trade)}</span>
            )}
          </div>
        </div>
        <div className="flex items-center gap-3 shrink-0 text-[10px]">
          <Stat
            label="Trades"
            value={`${row.trades}/${MIN_TRADES}`}
            tone={row.trades >= MIN_TRADES ? 'up' : 'neutral'}
          />
          <Stat
            label="Sharpe"
            value={formatNumber(row.sharpe, 2)}
            tone={row.sharpe >= 1.0 ? 'up' : row.sharpe >= 0.5 ? 'neutral' : 'down'}
          />
          <Stat
            label="Win %"
            value={`${formatNumber(row.win_rate * 100, 1)}%`}
            tone={row.win_rate >= effectiveWrFloor ? 'up' : 'neutral'}
          />
          <Stat
            label="P&L"
            value={`${row.total_pnl >= 0 ? '+' : ''}${formatNumber(row.total_pnl, 0)}`}
            tone={pnlOk ? 'up' : 'down'}
          />
          {row.qualification_ratio != null && (
            <Stat
              label="Qual ratio"
              value={formatNumber(row.qualification_ratio, 2)}
              tone={row.qualification_ratio >= MIN_QUAL_RATIO ? 'up' : 'neutral'}
            />
          )}
        </div>
      </div>

      {/* Progress bars */}
      <div className="grid grid-cols-3 gap-2">
        <ProgressBar label="Trades" pct={tradesPct} met={row.trades >= MIN_TRADES} />
        <ProgressBar label="Win rate" pct={wrPct} met={row.win_rate >= effectiveWrFloor} />
        <ProgressBar
          label={row.qualification_ratio != null ? 'Qual ratio' : 'Sharpe'}
          pct={qualPct}
          met={ratioMet}
        />
      </div>

      {/* Missing criteria */}
      {row.missing_criteria.length > 0 && (
        <div className="text-[10px] text-[var(--text-3)]">
          Missing:{' '}
          {row.missing_criteria.map((m, i) => (
            <span key={i}>
              {i > 0 && ' · '}
              <span className="text-[var(--status-warning)]">{m}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="text-right">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[11px]',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-1)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function ProgressBar({
  label,
  pct,
  met,
}: {
  label: string
  pct: number
  met: boolean
}) {
  return (
    <div className="space-y-0.5">
      <div className="flex items-center justify-between text-[9px] text-[var(--text-3)]">
        <span>{label}</span>
        <span className={met ? 'text-[var(--pnl-up)]' : ''}>{Math.round(pct)}%</span>
      </div>
      <div className="h-1 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
        <div
          className="h-full rounded-[1px] transition-all"
          style={{
            width: `${pct}%`,
            backgroundColor: met
              ? 'var(--pnl-up)'
              : pct >= 75
                ? 'var(--status-warning)'
                : 'var(--accent-primary)',
          }}
        />
      </div>
    </div>
  )
}
