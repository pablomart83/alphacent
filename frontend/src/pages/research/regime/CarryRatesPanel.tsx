import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber } from '@/lib/utils'
import type { CarryRates } from '../useResearchData'

interface CarryRatesPanelProps {
  data: CarryRates | undefined
  loading?: boolean
}

interface Row {
  pair: string
  diff: number
}

export function CarryRatesPanel({ data, loading }: CarryRatesPanelProps) {
  const rows: Row[] = []
  if (data) {
    for (const [pair, entry] of Object.entries(data)) {
      const diff =
        entry && typeof entry === 'object' && 'differential' in entry
          ? Number((entry as { differential?: number }).differential ?? 0)
          : typeof entry === 'number'
            ? entry
            : 0
      rows.push({ pair, diff })
    }
  }
  rows.sort((a, b) => Math.abs(b.diff) - Math.abs(a.diff))

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[200px]">
      <SectionLabel className="mb-0">Forex carry differentials</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : rows.length === 0 ? (
        <div className="text-[11px] text-[var(--text-2)]">No carry data.</div>
      ) : (
        <div className="space-y-1 text-[10px]">
          {rows.slice(0, 8).map((r) => (
            <div key={r.pair} className="flex items-center justify-between">
              <span className="mono text-[var(--text-1)]">{r.pair.toUpperCase()}</span>
              <span
                className={cn(
                  'mono tabular-nums',
                  r.diff > 0
                    ? 'text-[var(--pnl-up)]'
                    : r.diff < 0
                      ? 'text-[var(--pnl-down)]'
                      : 'text-[var(--text-2)]',
                )}
              >
                {r.diff > 0 ? '+' : ''}
                {formatNumber(r.diff, 2)}%
              </span>
            </div>
          ))}
        </div>
      )}
    </Card>
  )
}
