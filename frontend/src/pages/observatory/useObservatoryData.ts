import { useMemo } from 'react'
import { useTradingMode } from '@/stores'
import type { EquityInterval, EquityPeriod } from '@/components/trading/EquityChart'
import {
  useAutonomousStatus,
  useDashboardSummary,
  useLiveSummary,
  usePerformanceAnalytics,
  usePipelineCounts,
  useSpyBenchmark,
} from '@/pages/command/useCommandData'
import {
  useAdvancedRisk,
  useRiskLimits,
  useRiskMetrics,
  useSystemStatus,
  useDataSyncStatus,
} from '@/pages/guard/useGuardData'

/**
 * Observatory data layer — a thin composition over the EXISTING page hooks.
 *
 * Deliberately adds no new backend surface: every field the Observatory shows
 * is already served by an endpoint the other pages consume, and because the
 * query keys match, TanStack Query dedupes the fetches across pages. This keeps
 * metric logic in one place (the backend analytics functions) and means the
 * Observatory can never drift from Command/Guard/Book.
 */

export interface FundOverview {
  equity: number | null
  todayPnl: number | null
  todayPnlPct: number | null
  monthReturnPct: number | null
  weekReturnPct: number | null
  unrealizedPnl: number | null
  availableCash: number | null
  sharpe: number | null
  sortino: number | null
  maxDrawdownPct: number | null
  currentDrawdownPct: number | null
  /** Gross exposure as % of equity (invested / equity). */
  grossExposurePct: number | null
  /** Portfolio exposure limit as % (from risk limits), for the progress bar. */
  exposureLimitPct: number | null
  netExposurePct: number | null
  winRate30d: number | null
  alphaVsSpyPct: number | null
  regime: string | null
  regimeConfidence: number | null
  regimeDataQuality: string | null
  regimeDescription: string | null
  liveEnabled: boolean
  liveAuthorisations: number
  /** Most-recent successful data touch (ISO) — drives the freshness dot. */
  dataUpdatedAt: number | null
  lastSyncAt: string | null
  systemState: string | null
}

function pct(value: number | null | undefined): number | null {
  return value == null || Number.isNaN(value) ? null : value
}

export function useObservatoryData(period: EquityPeriod, interval: EquityInterval) {
  const mode = useTradingMode((s) => s.mode)

  const dashboard = useDashboardSummary(interval)
  const performance = usePerformanceAnalytics(period, interval)
  const spy = useSpyBenchmark(period, true)
  const spyAll = useSpyBenchmark('ALL', true)
  const live = useLiveSummary()
  const risk = useRiskMetrics()
  const riskLimits = useRiskLimits()
  const advancedRisk = useAdvancedRisk()
  const autonomous = useAutonomousStatus()
  const pipeline = usePipelineCounts(autonomous.data?.cycle_stats?.proposals_generated)
  const systemStatus = useSystemStatus()
  const dataSync = useDataSyncStatus()

  const overview = useMemo<FundOverview>(() => {
    const d = dashboard.data
    const p = performance.data
    const r = risk.data
    const l = riskLimits.data
    const adv = advancedRisk.data

    const today = d?.pnl_periods?.find((x) => x.label === 'Today')
    const week = d?.pnl_periods?.find((x) => x.label === 'Week')
    const month = d?.pnl_periods?.find((x) => x.label === 'Month')

    const equity = d?.account_equity ?? null
    const invested = d?.total_invested ?? null
    const grossExposurePct =
      equity != null && equity > 0 && invested != null ? (invested / equity) * 100 : null

    // Risk-limit max_portfolio_exposure is a fraction (e.g. 0.3). Normalise to %.
    const exposureLimitPct =
      l?.max_portfolio_exposure != null
        ? l.max_portfolio_exposure <= 1
          ? l.max_portfolio_exposure * 100
          : l.max_portfolio_exposure
        : null

    return {
      equity,
      todayPnl: today?.pnl_absolute ?? null,
      todayPnlPct: today?.pnl_percent ?? null,
      weekReturnPct: pct(week?.pnl_percent),
      monthReturnPct: pct(month?.pnl_percent),
      unrealizedPnl: d?.total_unrealized_pnl ?? null,
      availableCash: d?.available_cash ?? null,
      sharpe: pct(p?.sharpe_ratio),
      sortino: pct(p?.sortino_ratio),
      maxDrawdownPct: p?.max_drawdown != null ? -Math.abs(p.max_drawdown) : null,
      currentDrawdownPct: r?.current_drawdown != null ? -Math.abs(r.current_drawdown) : null,
      grossExposurePct,
      exposureLimitPct,
      netExposurePct: adv?.directional_exposure?.net_pct ?? null,
      winRate30d: d?.quick_stats?.win_rate_30d ?? null,
      alphaVsSpyPct: pct(p?.alpha_vs_spy),
      regime: d?.market_regime?.current_regime ?? null,
      regimeConfidence: autonomous.data?.market_confidence ?? null,
      regimeDataQuality: autonomous.data?.data_quality ?? null,
      regimeDescription: d?.market_regime?.regime_description ?? null,
      liveEnabled: Boolean(live.data?.live_enabled),
      liveAuthorisations: live.data?.active_live_authorizations ?? 0,
      dataUpdatedAt: dashboard.dataUpdatedAt || null,
      lastSyncAt: dataSync.data?.last_sync_at ?? null,
      systemState: systemStatus.data?.state ?? null,
    }
  }, [
    dashboard.data,
    dashboard.dataUpdatedAt,
    performance.data,
    risk.data,
    riskLimits.data,
    advancedRisk.data,
    autonomous.data,
    live.data,
    dataSync.data,
    systemStatus.data,
  ])

  return {
    mode,
    overview,
    queries: {
      dashboard,
      performance,
      spy,
      spyAll,
      live,
      risk,
      riskLimits,
      advancedRisk,
      autonomous,
      pipeline,
      systemStatus,
      dataSync,
    },
  }
}
