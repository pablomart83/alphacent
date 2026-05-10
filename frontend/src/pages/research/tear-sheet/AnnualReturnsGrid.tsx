import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { CalendarRange } from 'lucide-react'
import { cn, formatNumber } from '@/lib/utils'
import type { AnnualReturn } from '../useResearchData'

interface AnnualReturnsGridProps {
  rows: AnnualReturn[] | undefined
  loading?: boolean
}

export function AnnualReturnsGrid({ rows, loading }: AnnualReturnsGridProps) {
  const data = rows ?? []

  if (loading && !data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Annual returns</SectionLabel>
        <div className="h-[120px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Annual returns</SectionLabel>
        <EmptyState
          icon={CalendarRange}
          title="No annual returns yet"
          description="Per-year returns populate once at least one full month of snapshots exists."
          className="py-6"
        />
      </section>
    )
  }

  const max = Math.max(...data.map((d) => Math.abs(d.return_pct)), 1)

  return (
    <section className="space-y-1.5">
      <SectionLabel>Annual returns</SectionLabel>
      <div className="grid grid-cols-2 md:grid-cols-4 xl:grid-cols-6 gap-2">
        {data
          .slice()
          .sort((a, b) => a.year - b.year)
          .map((r) => {
            const pct = Math.min(100, (Math.abs(r.return_pct) / max) * 100)
            return (
              <div
                key={r.year}
                className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2.5 py-2"
              >
                <div className="flex items-baseline justify-between">
                  <span className="mono tabular-nums text-[11px] text-[var(--text-2)]">
                    {r.year}
                  </span>
                  <span
                    className={cn(
                      'mono tabular-nums text-[13px] font-semibold',
                      r.return_pct > 0
                        ? 'text-[var(--pnl-up)]'
                        : r.return_pct < 0
                          ? 'text-[var(--pnl-down)]'
                          : 'text-[var(--text-2)]',
                    )}
                  >
                    {r.return_pct > 0 ? '+' : ''}
                    {formatNumber(r.return_pct, 1)}%
                  </span>
                </div>
                <div className="mt-1 h-1.5 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
                  <div
                    className="h-full"
                    style={{
                      width: `${pct}%`,
                      backgroundColor: r.return_pct >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)',
                    }}
                  />
                </div>
              </div>
            )
          })}
      </div>
    </section>
  )
}
