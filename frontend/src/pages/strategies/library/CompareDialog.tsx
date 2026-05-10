import { Minus } from 'lucide-react'
import {
  Badge,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/primitives'
import { ConvictionBar } from '@/components/trading/ConvictionBar'
import { RegimePill } from '@/components/trading/RegimePill'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn, formatPercentage, formatTimestamp } from '@/lib/utils'
import type { StrategyRow } from '../useStrategiesData'

interface CompareDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  left: StrategyRow | null
  right: StrategyRow | null
}

interface MetricRow {
  label: string
  accessor: (s: StrategyRow) => string
  /** Returns -1/0/1 based on which side wins — used to highlight the winner. */
  compare?: (a: StrategyRow, b: StrategyRow) => -1 | 0 | 1
}

function num(v: number | null | undefined): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

const ROWS: MetricRow[] = [
  {
    label: 'Status',
    accessor: (s) => (s.status === 'DEMO' ? 'PAPER' : s.status),
  },
  {
    label: 'Category',
    accessor: (s) => (s.strategy_category ?? 'manual').replace(/_/g, ' '),
  },
  {
    label: 'Template',
    accessor: (s) => s.template_name ?? s.metadata?.template_name ?? '—',
  },
  {
    label: 'Regime',
    accessor: (s) => s.market_regime ?? s.metadata?.market_regime ?? '—',
  },
  {
    label: 'Sharpe',
    accessor: (s) => num(s.performance_metrics?.sharpe_ratio)?.toFixed(2) ?? '—',
    compare: (a, b) => {
      const av = num(a.performance_metrics?.sharpe_ratio) ?? -Infinity
      const bv = num(b.performance_metrics?.sharpe_ratio) ?? -Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Total return',
    accessor: (s) => {
      const v = num(s.performance_metrics?.total_return)
      return v == null ? '—' : formatPercentage(v * 100, { precision: 1, signed: true })
    },
    compare: (a, b) => {
      const av = num(a.performance_metrics?.total_return) ?? -Infinity
      const bv = num(b.performance_metrics?.total_return) ?? -Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Max drawdown',
    accessor: (s) => {
      const v = num(s.performance_metrics?.max_drawdown)
      return v == null ? '—' : `${(v * 100).toFixed(1)}%`
    },
    // Lower max DD (less negative) wins.
    compare: (a, b) => {
      const av = num(a.performance_metrics?.max_drawdown) ?? Infinity
      const bv = num(b.performance_metrics?.max_drawdown) ?? Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Win rate',
    accessor: (s) => {
      const v = num(s.performance_metrics?.win_rate)
      return v == null ? '—' : `${(v * 100).toFixed(0)}%`
    },
    compare: (a, b) => {
      const av = num(a.performance_metrics?.win_rate) ?? -Infinity
      const bv = num(b.performance_metrics?.win_rate) ?? -Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Trades',
    accessor: (s) => String(s.performance_metrics?.total_trades ?? 0),
    compare: (a, b) => {
      const av = a.performance_metrics?.total_trades ?? 0
      const bv = b.performance_metrics?.total_trades ?? 0
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Open positions',
    accessor: (s) => String(s.performance_metrics?.open_positions ?? 0),
  },
  {
    label: 'Conviction',
    accessor: (s) => {
      const v = s.metadata?.conviction_score
      return typeof v === 'number' ? v.toFixed(0) : '—'
    },
    compare: (a, b) => {
      const av = a.metadata?.conviction_score ?? -Infinity
      const bv = b.metadata?.conviction_score ?? -Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Alpha vs SPY',
    accessor: (s) => {
      const v = num(s.alpha_vs_spy)
      return v == null ? '—' : formatPercentage(v * 100, { precision: 2, signed: true })
    },
    compare: (a, b) => {
      const av = num(a.alpha_vs_spy) ?? -Infinity
      const bv = num(b.alpha_vs_spy) ?? -Infinity
      return av > bv ? -1 : av < bv ? 1 : 0
    },
  },
  {
    label: 'Health',
    accessor: (s) => {
      const v = s.performance_metrics?.health_score ?? s.metadata?.health_score
      return v == null ? '—' : `${v}/5`
    },
  },
  {
    label: 'Decay',
    accessor: (s) => {
      const v = s.performance_metrics?.decay_score ?? s.metadata?.decay_score
      return v == null ? '—' : `${v}/10`
    },
  },
  {
    label: 'Allocation',
    accessor: (s) => `${(s.allocation_percent ?? 0).toFixed(2)}%`,
  },
  {
    label: 'Activated',
    accessor: (s) => formatTimestamp(s.activated_at, 'date'),
  },
]

export function CompareDialog({ open, onOpenChange, left, right }: CompareDialogProps) {
  if (!left || !right) return null
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent size="xl" className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Compare strategies</DialogTitle>
          <DialogDescription>
            Side-by-side metrics. Winning values are highlighted where higher is better
            (except max drawdown, where lower is better).
          </DialogDescription>
        </DialogHeader>

        {/* Headers */}
        <div className="grid grid-cols-[160px_1fr_1fr] gap-3 items-start">
          <div />
          <StrategyHeaderCard strategy={left} accent="left" />
          <StrategyHeaderCard strategy={right} accent="right" />
        </div>

        {/* Metrics table */}
        <div className="grid grid-cols-[160px_1fr_1fr] gap-0 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] overflow-hidden">
          {ROWS.map((row, idx) => {
            const leftValue = row.accessor(left)
            const rightValue = row.accessor(right)
            const cmp = row.compare ? row.compare(left, right) : 0
            return (
              <div
                key={row.label}
                className="contents"
              >
                <div
                  className={cn(
                    'px-2 py-1.5 text-[10px] uppercase tracking-wide text-[var(--text-3)]',
                    idx > 0 && 'border-t border-[var(--border-subtle)]',
                  )}
                >
                  {row.label}
                </div>
                <CompareValue value={leftValue} winner={cmp === -1} idx={idx} />
                <CompareValue value={rightValue} winner={cmp === 1} idx={idx} />
              </div>
            )
          })}
        </div>

        {/* Regime / conviction visuals */}
        <div className="grid grid-cols-[160px_1fr_1fr] gap-3 mt-1">
          <div className="text-[10px] uppercase tracking-wide text-[var(--text-3)] pt-1">
            Conviction
          </div>
          <ConvictionVisual strategy={left} />
          <ConvictionVisual strategy={right} />
        </div>
      </DialogContent>
    </Dialog>
  )
}

function StrategyHeaderCard({
  strategy,
  accent,
}: {
  strategy: StrategyRow
  accent: 'left' | 'right'
}) {
  const status = strategy.status
  const statusVariant =
    status === 'LIVE'
      ? 'live'
      : status === 'PAPER' || status === 'DEMO'
        ? 'paper'
        : status === 'BACKTESTED'
          ? 'backtested'
          : status === 'RETIRED'
            ? 'retired'
            : 'info'
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-2">
      <div className="flex items-center gap-1.5 mb-1">
        <Badge variant={statusVariant} size="sm">
          {status === 'DEMO' ? 'PAPER' : status}
        </Badge>
        <span className="text-[9px] uppercase tracking-wide text-[var(--text-3)]">
          {accent === 'left' ? 'A' : 'B'}
        </span>
      </div>
      <div
        className="text-[12px] font-semibold text-[var(--text-0)] leading-tight truncate"
        title={strategy.name}
      >
        {strategy.name}
      </div>
      <div className="flex items-center gap-1 mt-1 flex-wrap">
        {strategy.market_regime && (
          <RegimePill regime={strategy.market_regime} size="sm" showConfidence={false} />
        )}
        {strategy.strategy_category && (
          <Badge variant="muted" size="sm">
            {strategy.strategy_category.replace(/_/g, ' ')}
          </Badge>
        )}
      </div>
    </div>
  )
}

function CompareValue({
  value,
  winner,
  idx,
}: {
  value: string
  winner: boolean
  idx: number
}) {
  // Try to detect percentage / number with sign for coloring
  const isPercent = /%$/.test(value)
  const numeric = isPercent ? Number(value.replace('%', '')) : NaN
  const isPnl = isPercent && !Number.isNaN(numeric) && /^[+-]/.test(value)
  return (
    <div
      className={cn(
        'px-2 py-1.5 text-[11px] mono tabular-nums',
        idx > 0 && 'border-t border-[var(--border-subtle)]',
        winner
          ? 'bg-[color-mix(in_oklab,var(--accent-primary)_10%,transparent)] text-[var(--text-0)] font-semibold'
          : 'text-[var(--text-1)]',
      )}
    >
      {isPnl && !Number.isNaN(numeric) ? (
        <PnLNumber value={numeric} format="percentage" precision={2} size="sm" showSign />
      ) : value === '—' ? (
        <span className="text-[var(--text-3)] inline-flex items-center gap-1">
          <Minus className="h-3 w-3" />
          not available
        </span>
      ) : (
        value
      )}
    </div>
  )
}

function ConvictionVisual({ strategy }: { strategy: StrategyRow }) {
  const score = strategy.metadata?.conviction_score
  if (score == null) {
    return (
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-2 text-[11px] text-[var(--text-3)]">
        No conviction score recorded
      </div>
    )
  }
  const breakdown = strategy.metadata?.conviction_score_breakdown
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] p-2">
      <ConvictionBar
        score={score}
        components={
          breakdown
            ? {
                wf_edge: breakdown.wf_edge ?? undefined,
                signal_quality: breakdown.signal_quality ?? undefined,
                regime_fit: breakdown.regime_fit ?? undefined,
                asset_tradability: breakdown.asset_tradability ?? undefined,
                fundamental: breakdown.fundamental ?? undefined,
                carry: breakdown.carry ?? undefined,
                crypto_cycle: breakdown.crypto_cycle ?? undefined,
                sentiment: breakdown.sentiment ?? undefined,
                factor: breakdown.factor ?? undefined,
              }
            : undefined
        }
        size="default"
        threshold={74}
        showValue
      />
    </div>
  )
}
