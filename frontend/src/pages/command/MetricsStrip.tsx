import { PnLNumber } from '@/components/trading/PnLNumber'
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
      <Tile label="Equity" value={formatCurrency(equity ?? 0, { precision: 0 })} mono />
      <TileFlash label="Daily P&L" value={dailyPnl ?? 0} format="currency" precision={0} />
      <TileFlash
        label="Daily %"
        value={dailyPnlPct ?? 0}
        format="percentage"
        precision={2}
      />
      <TileFlash label="Unrealized" value={unrealizedPnl ?? 0} format="currency" precision={0} />
      <Tile
        label="Win Rate (30d)"
        value={winRate30d == null ? '—' : formatPercentage(winRate30d, { precision: 1, signed: false })}
        mono
      />
      <Tile
        label="Sharpe (30d)"
        value={sharpe30d == null ? '—' : formatNumber(sharpe30d, 2)}
        mono
        emphasis={sharpe30d != null && sharpe30d >= 1 ? 'up' : sharpe30d != null && sharpe30d < 0 ? 'down' : 'default'}
      />
      <Tile
        label="Max DD"
        value={
          maxDrawdown == null
            ? '—'
            : formatPercentage(maxDrawdown, { precision: 1, signed: true })
        }
        emphasis="down"
        mono
      />
      <Tile label="Cash" value={formatCurrency(cash ?? 0, { precision: 0 })} mono />
    </div>
  )
}

function Tile({
  label,
  value,
  mono,
  emphasis = 'default',
}: {
  label: string
  value: React.ReactNode
  mono?: boolean
  emphasis?: 'default' | 'up' | 'down'
}) {
  const colour =
    emphasis === 'up'
      ? 'text-[var(--pnl-up)]'
      : emphasis === 'down'
        ? 'text-[var(--pnl-down)]'
        : 'text-[var(--text-0)]'
  return (
    <div className="flex flex-col gap-0.5 p-1.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)]">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium truncate">
        {label}
      </span>
      <span className={cn('text-[13px] font-semibold', mono && 'mono tabular-nums', colour)}>
        {value}
      </span>
    </div>
  )
}

function TileFlash({
  label,
  value,
  format,
  precision,
}: {
  label: string
  value: number
  format: 'currency' | 'percentage' | 'decimal'
  precision: number
}) {
  return (
    <div className="flex flex-col gap-0.5 p-1.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)]">
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium truncate">
        {label}
      </span>
      <PnLNumber value={value} format={format} precision={precision} size="md" />
    </div>
  )
}
