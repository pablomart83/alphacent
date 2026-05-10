import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import type { TransactionCostSavings } from '../useResearchData'

interface TransactionCostTileProps {
  data: TransactionCostSavings | undefined
  loading?: boolean
}

export function TransactionCostTile({ data, loading }: TransactionCostTileProps) {
  const before = Number(data?.before_costs ?? 0)
  const after = Number(data?.after_costs ?? 0)
  const savings = Number(data?.total_savings ?? 0)
  const pct = Number(data?.cost_as_percent_of_returns ?? 0)
  const tradesBefore = Number(data?.trades_before ?? 0)
  const tradesAfter = Number(data?.trades_after ?? 0)

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[260px]">
      <SectionLabel className="mb-0">Transaction-cost savings</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
              Savings (post-filter vs pre-filter)
            </div>
            <div
              className={cn(
                'mt-0.5 text-[22px] font-semibold mono tabular-nums leading-none',
                savings >= 0 ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]',
              )}
            >
              {formatCurrency(savings, { signed: true, precision: 0 })}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <Stat label="Before" value={formatCurrency(before, { precision: 0 })} />
            <Stat label="After" value={formatCurrency(after, { precision: 0 })} />
            <Stat label="Trades in" value={formatNumber(tradesBefore, 0)} />
            <Stat label="Trades out" value={formatNumber(tradesAfter, 0)} tone="up" />
            <Stat label="Cost %" value={`${formatNumber(pct, 2)}%`} />
          </div>
        </>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[12px]',
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
