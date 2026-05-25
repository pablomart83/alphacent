import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import type { EquityInterval, EquityPeriod } from '@/components/trading/EquityChart'
import type { PnLPeriodEntry } from './MultiTimeframeReturns'
import type { HealthScore } from './HealthScoreCard'
import type { AutonomousStatusShape } from './CycleStatusCard'
import type { PipelineCounts } from './StrategyPipelineCounts'
import { useLiveSummary as useLiveSummaryBase, type LiveSummary } from '@/pages/book/useBookData'

// Re-export for callers so nothing breaks.
export { useLiveSummaryBase as useLiveSummary }
export type LiveSummaryPayload = LiveSummary

/* ───────────── Response shapes ───────────── */

export interface EquityPointApi {
  date: string
  equity: number
  realized?: number | null
  benchmark?: number | null
}

export interface DrawdownPointApi {
  date: string
  drawdown_pct: number
}

export interface MarketRegimeInfoApi {
  current_regime: string
  regime_color?: string
  regime_description?: string
}

export interface SectorExposureApi {
  sector: string
  allocation_pct: number
  pnl: number
  pnl_pct: number
  position_count: number
}

export interface QuickStatsApi {
  open_positions: number
  active_strategies: number
  pending_orders: number
  todays_trades: number
  win_rate_30d: number
  sharpe_30d: number | null
}

export interface DashboardSummaryPayload {
  pnl_periods: PnLPeriodEntry[]
  equity_curve: EquityPointApi[]
  drawdown_data: DrawdownPointApi[]
  sector_exposure: SectorExposureApi[]
  market_regime: MarketRegimeInfoApi
  health_score: HealthScore
  quick_stats: QuickStatsApi
  account_balance: number
  account_equity: number
  available_cash: number
  total_unrealized_pnl: number
  total_invested: number
}

export interface PerformanceAnalyticsPayload {
  total_return: number
  total_return_dollars?: number | null
  realized_return?: number | null
  realized_return_dollars?: number | null
  spy_return?: number | null
  alpha_vs_spy?: number | null
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  equity_curve: Array<{
    timestamp: string
    equity: number
    return_pct?: number
    drawdown?: number
    realized?: number | null
  }>
  monthly_returns: Record<string, number>
  returns_distribution: Record<string, number>
  daily_returns_count?: number
}

export interface SPYBenchmarkPayload {
  data: Array<{ date: string; close: number }>
  inception_equity_base?: number | null
}

interface StrategySlim {
  id: string
  status: string
}

interface StrategiesSlimPayload {
  strategies: StrategySlim[]
  total_count: number
}

/* ───────────── Hooks ───────────── */

export function useDashboardSummary(interval: EquityInterval) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<DashboardSummaryPayload>({
    queryKey: ['dashboard', mode, interval],
    queryFn: () =>
      api.get<DashboardSummaryPayload>('/account/dashboard/summary', { mode, interval }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function usePerformanceAnalytics(period: EquityPeriod, interval: EquityInterval) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<PerformanceAnalyticsPayload>({
    queryKey: ['analytics-performance', mode, period, interval],
    queryFn: () =>
      api.get<PerformanceAnalyticsPayload>('/analytics/performance', {
        mode,
        period,
        interval,
      }),
    // Analytics are deep queries — poll every 2 min so users don't wait.
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useSpyBenchmark(period: EquityPeriod, enabled: boolean) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<SPYBenchmarkPayload>({
    queryKey: ['spy-benchmark', period, mode],
    queryFn: () => api.get<SPYBenchmarkPayload>('/analytics/spy-benchmark', { period, mode }),
    enabled,
    staleTime: 5 * 60_000,
  })
}

/** Lightweight 7d + 30d performance for the alpha generation tiles. */
export function useAlphaGeneration() {
  const mode = useTradingMode((s) => s.mode)
  const q7d = useQuery<PerformanceAnalyticsPayload>({
    queryKey: ['analytics-performance', mode, '1W', '1d'],
    queryFn: () =>
      api.get<PerformanceAnalyticsPayload>('/analytics/performance', {
        mode,
        period: '1W',
        interval: '1d',
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
  const q30d = useQuery<PerformanceAnalyticsPayload>({
    queryKey: ['analytics-performance', mode, '1M', '1d'],
    queryFn: () =>
      api.get<PerformanceAnalyticsPayload>('/analytics/performance', {
        mode,
        period: '1M',
        interval: '1d',
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
  return { q7d, q30d }
}

export function useAutonomousStatus() {
  return useQuery<AutonomousStatusShape>({
    queryKey: ['autonomous-status'],
    queryFn: () => api.get<AutonomousStatusShape>('/strategies/autonomous/status'),
    refetchInterval: 20_000,
    staleTime: 10_000,
  })
}

/** Strategy pipeline counts — uses `/strategies?slim=true&include_retired=true` and buckets by status. */
export function usePipelineCounts(autonomousProposalsFallback?: number) {
  const mode = useTradingMode((s) => s.mode)
  const query = useQuery<StrategiesSlimPayload>({
    queryKey: ['strategies', mode, { slim: true, include_retired: true }],
    queryFn: () =>
      api.get<StrategiesSlimPayload>('/strategies', {
        mode,
        slim: true,
        include_retired: true,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const counts = useMemo<PipelineCounts>(() => {
    const buckets: PipelineCounts = {
      proposed: 0,
      backtested: 0,
      paper: 0,
      live: 0,
      retired: 0,
    }
    const strategies = query.data?.strategies ?? []
    for (const s of strategies) {
      switch (s.status) {
        case 'PROPOSED':
          buckets.proposed++
          break
        case 'BACKTESTED':
          buckets.backtested++
          break
        case 'PAPER':
        case 'DEMO': // legacy
          buckets.paper++
          break
        case 'LIVE':
          buckets.live++
          break
        case 'RETIRED':
          buckets.retired++
          break
      }
    }
    // Fallback: if strategies table has no PROPOSED rows (they get promoted
    // immediately to BACKTESTED/PAPER in most cycles), use the latest cycle's
    // proposal count so the pipeline row isn't misleadingly 0.
    if (buckets.proposed === 0 && autonomousProposalsFallback) {
      buckets.proposed = autonomousProposalsFallback
    }
    return buckets
  }, [query.data, autonomousProposalsFallback])

  return { ...query, counts }
}
