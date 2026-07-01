import { StatTile } from '@/components/primitives'
import { cn, formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'

interface MetricsStripProps {
  equity: number | null | undefined
  dailyPnl: number | null | undefined
  dailyPnlPct: number | null | undefined
  unrealizedPnl: number | null | undefined
  winRate30d: number | null | undefined
  sharpe30d: number | null | undefined
  maxDrawdown: number | null | undefined
  cash: number | null | undefined
  className?: string
}

export function MetricsStrip({
  equity,
  dailyPnl,
  dailyPnlPct,
  unrealizedPnl,
  winRate30d,
  sharpe30d,
  maxDrawdown,
  cash,
  className,
}: MetricsStripProps) {
  return (
    <div className={cn('grid grid-cols-2 gap-2 p-2', className)}>
      <StatTile label="Equity" value={formatCurrency(equity ?? 0, { precision: 0 })} />
      <StatTile label="Daily P&L" pnl={{ value: dailyPnl ?? 0, format: 'currency', precision: 0 }} />
      <StatTile
        label="Daily %"
        pnl={{ value: dailyPnlPct ?? 0, format: 'percentage', precision: 2 }}
      />
      <StatTile
        label="Unrealized"
        pnl={{ value: unrealizedPnl ?? 0, format: 'currency', precision: 0 }}
      />
      <StatTile
        label="Win Rate (30d)"
        value={winRate30d == null ? '—' : formatPercentage(winRate30d, { precision: 1, signed: false })}
      />
      <StatTile
        label="Sharpe (30d)"
        value={sharpe30d == null ? '—' : formatNumber(sharpe30d, 2)}
        tone={sharpe30d != null && sharpe30d >= 1 ? 'up' : sharpe30d != null && sharpe30d < 0 ? 'down' : 'default'}
      />
      <StatTile
        label="Max DD"
        value={maxDrawdown == null ? '—' : formatPercentage(maxDrawdown, { precision: 1, signed: true })}
        tone="down"
      />
      <StatTile label="Cash" value={formatCurrency(cash ?? 0, { precision: 0 })} />
    </div>
  )
}
