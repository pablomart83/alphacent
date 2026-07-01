import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import type { EquityInterval, EquityPeriod } from '@/components/trading/EquityChart'
import {
  useAutonomousStatus,
  useDashboardSummary,
  useLiveSummary,
  usePerformanceAnalytics,
  usePipelineCounts,
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
 * Adds no new backend surface; query keys match the other pages so TanStack
 * Query dedupes every fetch. Metric logic stays server-side.
 */

export interface FundOverview {
  equity: number | null
  todayPnl: number | null
  todayPnlPct: number | null
  weekReturnPct: number | null
  monthReturnPct: number | null
  allTimeReturnPct: number | null
  unrealizedPnl: number | null
  availableCash: number | null
  sharpe: number | null
  sortino: number | null
  maxDrawdownPct: number | null
  currentDrawdownPct: number | null
  grossExposurePct: number | null
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
  dataUpdatedAt: number | null
  lastSyncAt: string | null
  systemState: string | null
  /** Equity series (active account) for the header sparkline. */
  equitySeries: number[]
}

export interface AccountSplit {
  demoEquity: number | null
  demoOpenPositions: number | null
  demoUnrealized: number | null
  liveVirtualEquity: number | null
  liveRealEquity: number | null
  liveOpenPositions: number | null
  liveTodayReal: number | null
  liveEnabled: boolean
}

interface DemoMini {
  account_equity: number
  total_unrealized_pnl: number
  quick_stats: { open_positions: number }
}

/** DEMO account NAV — independent of the toggle so the split always shows both. */
function useDemoNav() {
  return useQuery<DemoMini>({
    queryKey: ['dashboard-mini', 'DEMO'],
    queryFn: () => api.get<DemoMini>('/account/dashboard/summary', { mode: 'DEMO', interval: '1d' }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

function num(value: number | null | undefined): number | null {
  return value == null || Number.isNaN(value) ? null : value
}

export function useObservatoryData(period: EquityPeriod, interval: EquityInterval) {
  const mode = useTradingMode((s) => s.mode)

  const dashboard = useDashboardSummary(interval)
  const performance = usePerformanceAnalytics(period, interval)
  const live = useLiveSummary()
  const demoNav = useDemoNav()
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

    const period_ = (label: string) => d?.pnl_periods?.find((x) => x.label === label)
    const today = period_('Today')
    const week = period_('This Week')
    const month = period_('This Month')
    const allTime = period_('All-Time')

    const equity = d?.account_equity ?? null
    const invested = d?.total_invested ?? null
    const grossExposurePct =
      equity != null && equity > 0 && invested != null ? (invested / equity) * 100 : null
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
      weekReturnPct: num(week?.pnl_percent),
      monthReturnPct: num(month?.pnl_percent),
      allTimeReturnPct: num(allTime?.pnl_percent),
      unrealizedPnl: d?.total_unrealized_pnl ?? null,
      availableCash: d?.available_cash ?? null,
      sharpe: num(p?.sharpe_ratio),
      sortino: num(p?.sortino_ratio),
      maxDrawdownPct: p?.max_drawdown != null ? -Math.abs(p.max_drawdown) : null,
      currentDrawdownPct: r?.current_drawdown != null ? -Math.abs(r.current_drawdown) : null,
      grossExposurePct,
      exposureLimitPct,
      netExposurePct: adv?.directional_exposure?.net_pct ?? null,
      winRate30d: d?.quick_stats?.win_rate_30d ?? null,
      alphaVsSpyPct: num(p?.alpha_vs_spy),
      regime: d?.market_regime?.current_regime ?? null,
      regimeConfidence: autonomous.data?.market_confidence ?? null,
      regimeDataQuality: autonomous.data?.data_quality ?? null,
      regimeDescription: d?.market_regime?.regime_description ?? null,
      liveEnabled: Boolean(live.data?.live_enabled),
      liveAuthorisations: live.data?.active_live_authorizations ?? 0,
      dataUpdatedAt: dashboard.dataUpdatedAt || null,
      lastSyncAt: dataSync.data?.last_sync_at ?? null,
      systemState: systemStatus.data?.state ?? null,
      equitySeries: (d?.equity_curve ?? []).map((pt) => pt.equity).filter((v) => Number.isFinite(v)),
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

  const split = useMemo<AccountSplit>(
    () => ({
      demoEquity: demoNav.data?.account_equity ?? null,
      demoOpenPositions: demoNav.data?.quick_stats?.open_positions ?? null,
      demoUnrealized: demoNav.data?.total_unrealized_pnl ?? null,
      liveVirtualEquity: live.data?.virtual_equity ?? null,
      liveRealEquity: live.data?.real_equity ?? null,
      liveOpenPositions: live.data?.open_positions ?? null,
      liveTodayReal: live.data?.today_pnl_real ?? null,
      liveEnabled: Boolean(live.data?.live_enabled),
    }),
    [demoNav.data, live.data],
  )

  return {
    mode,
    overview,
    split,
    queries: {
      dashboard,
      performance,
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
