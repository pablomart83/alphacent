import { useMemo, useState } from 'react'
import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useResearchStore } from '@/stores'
import { useAnalyticsPerformance, useSpyBenchmark } from '../useResearchData'
import { PerformanceTiles } from './PerformanceTiles'
import { EquityCurvePanel } from './EquityCurvePanel'
import { ReturnsDistributionHistogram } from './ReturnsDistributionHistogram'
import { MonthlyReturnsHeatmap } from './MonthlyReturnsHeatmap'
import { AnnualReturnsBar } from './AnnualReturnsBar'
import { PipelineFunnelPanel } from './PipelineFunnelPanel'

/**
 * Performance tab — the default landing tab.
 *
 *   1. Tile strip: total return, Sharpe, Sortino, max DD, win rate,
 *      profit factor, daily returns count.
 *   2. Equity curve with optional SPY overlay, realised line and
 *      drawdown pane.
 *   3. Returns distribution histogram with μ and ±1σ guides.
 *   4. Monthly returns heatmap — years × months.
 *   5. Annual returns bar chart.
 */
export function PerformanceTab() {
  const period = useResearchStore((s) => s.period)
  const interval = useResearchStore((s) => s.interval)
  const performance = useAnalyticsPerformance(period, interval)
  const spy = useSpyBenchmark(period)

  const [showBenchmark, setShowBenchmark] = useState(true)
  const [showRealized, setShowRealized] = useState(true)
  const [showDrawdown, setShowDrawdown] = useState(true)

  const monthlyEntries = useMemo(() => {
    if (!performance.data?.monthly_returns) return []
    return Object.entries(performance.data.monthly_returns)
      .map(([key, pct]) => {
        const [y, m] = key.split('-')
        const year = Number(y)
        const month = Number(m)
        if (!Number.isFinite(year) || !Number.isFinite(month)) return null
        return { year, month, return_pct: pct }
      })
      .filter((e): e is { year: number; month: number; return_pct: number } => e != null)
  }, [performance.data?.monthly_returns])

  const annualEntries = useMemo(() => {
    if (!monthlyEntries.length) return []
    const by = new Map<number, number>()
    for (const m of monthlyEntries) {
      // Compound monthly percentage returns: (1+r/100) product − 1
      const prev = by.get(m.year)
      const factor = 1 + m.return_pct / 100
      by.set(m.year, prev == null ? factor : prev * factor)
    }
    return Array.from(by.entries())
      .map(([year, factor]) => ({ year, return_pct: (factor - 1) * 100 }))
      .sort((a, b) => a.year - b.year)
  }, [monthlyEntries])

  if (performance.isError) {
    const info = classifyError(performance.error, 'performance analytics')
    return (
      <ErrorState
        title="Couldn't load performance analytics"
        message={info.message}
        onRetry={() => performance.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <PerformanceTiles data={performance.data} loading={performance.isLoading} />
      <EquityCurvePanel
        equityCurve={performance.data?.equity_curve}
        spyData={spy.data?.data}
        loading={performance.isLoading}
        showBenchmark={showBenchmark}
        onShowBenchmarkChange={setShowBenchmark}
        showRealized={showRealized}
        onShowRealizedChange={setShowRealized}
        showDrawdown={showDrawdown}
        onShowDrawdownChange={setShowDrawdown}
      />
      <PipelineFunnelPanel />
      <ReturnsDistributionHistogram
        equityCurve={performance.data?.equity_curve}
        loading={performance.isLoading}
      />
      <MonthlyReturnsHeatmap
        entries={monthlyEntries}
        loading={performance.isLoading}
      />
      <AnnualReturnsBar data={annualEntries} loading={performance.isLoading} />
    </div>
  )
}
