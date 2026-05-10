import { useMemo } from 'react'
import { PnLNumber } from '@/components/trading/PnLNumber'
import {
  EquityChart,
  type EquityInterval,
  type EquityPeriod,
  type EquityPoint,
  type DrawdownPoint,
  type BenchmarkPoint,
} from '@/components/trading/EquityChart'
import type {
  DashboardSummaryPayload,
  PerformanceAnalyticsPayload,
  SPYBenchmarkPayload,
} from './useCommandData'
import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'

interface EquityPanelProps {
  dashboard: DashboardSummaryPayload | undefined
  analytics: PerformanceAnalyticsPayload | undefined
  spy: SPYBenchmarkPayload | undefined
  isLoadingDashboard: boolean
  isLoadingAnalytics: boolean
  error: unknown
  onRetry: () => void

  period: EquityPeriod
  onPeriodChange: (p: EquityPeriod) => void
  interval: EquityInterval
  onIntervalChange: (iv: EquityInterval) => void

  showBenchmark: boolean
  onShowBenchmarkChange: (v: boolean) => void
  showRealized: boolean
  onShowRealizedChange: (v: boolean) => void
  showDrawdown: boolean
  onShowDrawdownChange: (v: boolean) => void

  fullscreen: boolean
  onFullscreenToggle: () => void
}

export function EquityPanel(props: EquityPanelProps) {
  const { dashboard, analytics, spy, error } = props

  // Prefer analytics curve (richer, scoped to selected period) over dashboard's 90d window.
  const equityData = useMemo<EquityPoint[]>(() => {
    if (analytics?.equity_curve?.length) {
      return analytics.equity_curve.map((p) => ({
        date: p.timestamp,
        equity: p.equity,
      }))
    }
    if (dashboard?.equity_curve?.length) {
      return dashboard.equity_curve.map((p) => ({
        date: p.date,
        equity: p.equity,
        realized: p.realized ?? null,
      }))
    }
    return []
  }, [analytics?.equity_curve, dashboard?.equity_curve])

  const drawdownData = useMemo<DrawdownPoint[]>(() => {
    if (analytics?.equity_curve?.length) {
      return analytics.equity_curve
        .filter((p) => p.drawdown != null)
        .map((p) => ({ date: p.timestamp, drawdown_pct: Number(p.drawdown) }))
    }
    return dashboard?.drawdown_data ?? []
  }, [analytics?.equity_curve, dashboard?.drawdown_data])

  const benchmark = useMemo<BenchmarkPoint[]>(() => spy?.data ?? [], [spy?.data])

  if (error) {
    const info = classifyError(error, 'equity curve')
    return (
      <div className="h-full flex items-center justify-center">
        <ErrorState
          title="Couldn't load equity curve"
          message={info.message}
          onRetry={props.onRetry}
        />
      </div>
    )
  }

  const returnForHero = useMemo(() => {
    if (!dashboard?.pnl_periods?.length) return null
    const today = dashboard.pnl_periods.find((p) => p.label === 'Today')
    return today ?? dashboard.pnl_periods[0]
  }, [dashboard])

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Hero */}
      <div className="flex items-baseline gap-3 px-3 py-2 border-b border-[var(--border-subtle)] shrink-0">
        <div className="flex flex-col">
          <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)] font-medium">
            Today's Return
          </span>
          {returnForHero ? (
            <div className="flex items-baseline gap-2">
              <PnLNumber
                value={returnForHero.pnl_absolute}
                format="currency"
                precision={0}
                size="2xl"
              />
              <PnLNumber
                value={returnForHero.pnl_percent}
                format="percentage"
                precision={2}
                size="lg"
              />
            </div>
          ) : (
            <span className="text-[var(--text-3)] text-[22px] font-bold mono">—</span>
          )}
        </div>
        <div className="ml-auto text-[10px] text-[var(--text-3)] uppercase tracking-wider">
          {props.interval.toUpperCase()} · {props.period}
        </div>
      </div>

      {/* Chart */}
      <div className="flex-1 min-h-0">
        <EquityChart
          equityData={equityData}
          spyData={benchmark}
          drawdownData={drawdownData}
          period={props.period}
          onPeriodChange={props.onPeriodChange}
          interval={props.interval}
          onIntervalChange={props.onIntervalChange}
          showBenchmark={props.showBenchmark}
          onShowBenchmarkChange={props.onShowBenchmarkChange}
          showRealized={props.showRealized}
          onShowRealizedChange={props.onShowRealizedChange}
          showDrawdown={props.showDrawdown}
          onShowDrawdownChange={props.onShowDrawdownChange}
          fullscreen={props.fullscreen}
          onFullscreenToggle={props.onFullscreenToggle}
          loading={props.isLoadingDashboard || props.isLoadingAnalytics}
        />
      </div>
    </div>
  )
}
