import { useMemo } from 'react'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'
import type { EquityPeriod } from '@/components/trading/EquityChart'

export interface PnLPeriodEntry {
  label: string
  pnl_absolute: number
  pnl_percent: number
}

interface MultiTimeframeReturnsProps {
  periods: PnLPeriodEntry[] | undefined
  /** Alpha vs SPY per period (optional — backend exposes via analytics/spy-benchmark in Sprint 10). */
  alphaByLabel?: Record<string, number>
  selectedChartPeriod: EquityPeriod
  onChartPeriodChange: (p: EquityPeriod) => void
  className?: string
}

const LABEL_TO_PERIOD: Record<string, EquityPeriod> = {
  Today: '1W',
  'This Week': '1W',
  'This Month': '1M',
  'All-Time': 'ALL',
}

export function MultiTimeframeReturns({
  periods,
  alphaByLabel,
  selectedChartPeriod,
  onChartPeriodChange,
  className,
}: MultiTimeframeReturnsProps) {
  const rows = useMemo(() => periods ?? [], [periods])

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Returns</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
        <table className="w-full">
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td
                  colSpan={3}
                  className="px-2 py-3 text-center text-[11px] text-[var(--text-3)]"
                >
                  No return data yet
                </td>
              </tr>
            )}
            {rows.map((row) => {
              const target = LABEL_TO_PERIOD[row.label] ?? 'ALL'
              const isActive = target === selectedChartPeriod
              const alpha = alphaByLabel?.[row.label]
              return (
                <tr
                  key={row.label}
                  onClick={() => onChartPeriodChange(target)}
                  className={cn(
                    'cursor-pointer transition-colors',
                    isActive
                      ? 'bg-[var(--bg-active)]'
                      : 'hover:bg-[var(--bg-hover)]',
                  )}
                >
                  <td className="px-2 py-1 text-[11px] text-[var(--text-1)] font-medium">
                    {row.label}
                  </td>
                  <td className="px-2 py-1 text-right">
                    <PnLNumber value={row.pnl_absolute} format="currency" precision={0} size="sm" />
                  </td>
                  <td className="px-2 py-1 text-right">
                    <PnLNumber value={row.pnl_percent} format="percentage" precision={2} size="sm" />
                  </td>
                  {alpha != null && (
                    <td className="px-2 py-1 text-right">
                      <PnLNumber
                        value={alpha}
                        format="percentage"
                        precision={2}
                        size="sm"
                        prefix={<span className="text-[9px] text-[var(--text-3)] mr-0.5">α</span>}
                      />
                    </td>
                  )}
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
