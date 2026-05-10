import { useMemo } from 'react'
import { EquityChart } from '@/components/trading/EquityChart'
import { SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { useResearchStore } from '@/stores'
import type {
  EquityCurvePointApi,
  SpyBenchmarkPoint,
} from '../useResearchData'

interface EquityCurvePanelProps {
  equityCurve: EquityCurvePointApi[] | undefined
  spyData: SpyBenchmarkPoint[] | undefined
  loading: boolean
  showBenchmark: boolean
  onShowBenchmarkChange: (v: boolean) => void
  showRealized: boolean
  onShowRealizedChange: (v: boolean) => void
  showDrawdown: boolean
  onShowDrawdownChange: (v: boolean) => void
}

export function EquityCurvePanel({
  equityCurve,
  spyData,
  loading,
  showBenchmark,
  onShowBenchmarkChange,
  showRealized,
  onShowRealizedChange,
  showDrawdown,
  onShowDrawdownChange,
}: EquityCurvePanelProps) {
  const period = useResearchStore((s) => s.period)
  const interval = useResearchStore((s) => s.interval)
  const setPeriod = useResearchStore((s) => s.setPeriod)
  const setInterval = useResearchStore((s) => s.setInterval)

  const { points, dd } = useMemo(() => {
    const curve = equityCurve ?? []
    const points = curve.map((p) => ({
      date: p.timestamp,
      equity: p.equity,
      realized: p.realized ?? null,
    }))
    const dd = curve.map((p) => ({ date: p.timestamp, drawdown_pct: -Math.abs(p.drawdown) }))
    return { points, dd }
  }, [equityCurve])

  return (
    <section className="space-y-1.5">
      <SectionLabel>Equity curve</SectionLabel>
      {loading && !equityCurve ? (
        <Skeleton variant="chart" />
      ) : (
        <div className="h-[460px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] overflow-hidden">
          <EquityChart
            equityData={points}
            spyData={spyData}
            drawdownData={dd}
            period={period}
            onPeriodChange={setPeriod}
            interval={interval}
            onIntervalChange={setInterval}
            showBenchmark={showBenchmark}
            onShowBenchmarkChange={onShowBenchmarkChange}
            showRealized={showRealized}
            onShowRealizedChange={onShowRealizedChange}
            showDrawdown={showDrawdown}
            onShowDrawdownChange={onShowDrawdownChange}
          />
        </div>
      )}
    </section>
  )
}
