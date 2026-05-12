import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import type { ResearchPeriod, ResearchInterval } from '@/stores'

/**
 * Data hooks for the Research surface.
 *
 * All endpoints are read-only analytics — no mutations live here.
 * Research is cold data: poll every 2 min rather than tracking WS events.
 * Query keys include mode+period so flipping DEMO/LIVE or period refreshes
 * the view without stale data crossover.
 */

/* ============================================================
 * Response shapes — mirror backend Pydantic models exactly.
 * ============================================================ */

export interface EquityCurvePointApi {
  timestamp: string
  equity: number
  drawdown: number
  realized?: number | null
}

export interface PerformanceAnalyticsPayload {
  total_return: number
  total_return_dollars?: number | null
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  profit_factor: number
  total_trades: number
  equity_curve: EquityCurvePointApi[]
  monthly_returns: Record<string, number>
  returns_distribution: Record<string, number>
  daily_returns_count: number
}

export interface SpyBenchmarkPoint {
  date: string
  close: number
}

export interface SpyBenchmarkPayload {
  data: SpyBenchmarkPoint[]
}

export interface StrategyAttribution {
  strategy_id: string
  strategy_name: string
  total_return: number
  contribution_percent: number
  sharpe_ratio: number
  total_trades: number
  win_rate: number
}

export interface SectorAttribution {
  sector: string
  portfolio_weight: number
  benchmark_weight: number
  portfolio_return: number
  benchmark_return: number
  allocation_effect: number
  selection_effect: number
  interaction_effect: number
  total_contribution: number
}

export interface CumulativeEffectPoint {
  date: string
  allocation: number
  selection: number
  interaction: number
}

export interface PerformanceAttributionPayload {
  sectors: SectorAttribution[]
  cumulative_effects: CumulativeEffectPoint[]
}

export interface TradeAnalyticsPayload {
  total_trades: number
  winning_trades: number
  losing_trades: number
  win_rate: number
  avg_win: number
  avg_loss: number
  profit_factor: number
  avg_holding_time_hours: number
  largest_win: number
  largest_loss: number
  win_loss_distribution: Record<string, number>
  pnl_by_day: Record<string, number>
  pnl_by_hour: Record<string, number>
}

export interface RollingStatsPoint {
  date: string
  value: number
}

export interface RollingStatsPayload {
  rolling_sharpe: RollingStatsPoint[]
  rolling_beta: RollingStatsPoint[]
  rolling_alpha: RollingStatsPoint[]
  rolling_volatility: RollingStatsPoint[]
  probabilistic_sharpe: number
  information_ratio: number
  treynor_ratio: number
  tracking_error: number
}

export interface PerformanceStatsPayload {
  total_return?: number
  sharpe_ratio?: number
  sortino_ratio?: number
  max_drawdown?: number
  win_rate?: number
  profit_factor?: number
  calmar_ratio?: number
  volatility?: number
  [key: string]: unknown
}

/* ============================================================
 * Regime (Sprint 11)
 * ============================================================ */

export interface RegimeSnapshot {
  regime: string
  confidence?: number
  data_quality?: string
  change_20d?: number
  change_50d?: number
  atr_ratio?: number
  symbols?: string[]
  error?: string
}

export interface RegimePerformanceRow {
  regime: string
  total_return: number
  sharpe: number
  trades: number
  win_rate: number
}

export interface RegimeTransition {
  date: string
  from_regime: string
  to_regime: string
}

export interface StrategyRegimeRow {
  strategy: string
  trending_up: number
  trending_down: number
  ranging: number
  volatile: number
}

export interface MarketContext {
  vix?: number
  vix_change?: number
  ten_year_yield?: number
  two_year_yield?: number
  yield_curve_spread?: number
  fed_funds_rate?: number
  cpi?: number
  gdp_nowcast?: number
  ism_pmi?: number
  [key: string]: unknown
}

export interface CryptoCycle {
  phase?: string
  days_since_halving?: number
  days_until_halving?: number
  recommendation?: string
  [key: string]: unknown
}

export interface CarryRates {
  [pair: string]: { differential?: number; base?: number; quote?: number } | unknown
}

export interface MarketQuality {
  score: number
  grade: string
  components?: Record<string, number>
  reason?: string
}

export interface RegimeComprehensivePayload {
  current_regimes?: Record<string, RegimeSnapshot>
  performance_by_regime?: RegimePerformanceRow[]
  regime_transitions?: RegimeTransition[]
  strategy_regime_performance?: StrategyRegimeRow[]
  market_context?: MarketContext
  crypto_cycle?: CryptoCycle
  carry_rates?: CarryRates
  market_quality?: MarketQuality
}

/* ============================================================
 * Alpha Edge
 * ============================================================ */

export interface FundamentalStats {
  symbols_filtered: number
  symbols_passed: number
  pass_rate: number
  failure_reasons: Record<string, number>
  checks_summary: Record<string, Record<string, number>>
}

export interface MLStats {
  signals_filtered: number
  signals_passed: number
  avg_confidence: number
  model_accuracy?: number | null
  model_precision?: number | null
  model_recall?: number | null
  model_f1_score?: number | null
  last_trained?: string | null
}

export interface ConvictionRange {
  range: string
  count: number
  avg_score?: number
  win_rate?: number
  avg_pnl?: number
  [key: string]: unknown
}

export interface ConvictionDistributionPayload {
  score_ranges: ConvictionRange[]
  avg_score: number
  median_score: number
  min_score: number
  max_score: number
}

export interface TemplatePerformance {
  template: string
  trades: number
  win_rate: number
  total_return: number
  sharpe_ratio: number
  avg_hold_time_hours: number
}

export interface TransactionCostSavings {
  before_costs: number
  after_costs: number
  total_savings: number
  cost_as_percent_of_returns: number
  trades_before: number
  trades_after: number
}

/* ============================================================
 * Tear Sheet
 * ============================================================ */

export interface UnderwaterPoint {
  date: string
  drawdown_pct: number
}

export interface WorstDrawdown {
  rank: number
  start_date: string
  trough_date: string
  recovery_date?: string | null
  depth_pct: number
  duration_days: number
  recovery_days?: number | null
}

export interface ReturnBin {
  bin: number
  count: number
}

export interface AnnualReturn {
  year: number
  return_pct: number
}

export interface MonthlyReturn {
  year: number
  month: number
  return_pct: number
}

export interface TearSheetPayload {
  underwater_plot: UnderwaterPoint[]
  worst_drawdowns: WorstDrawdown[]
  return_distribution: ReturnBin[]
  skew: number
  kurtosis: number
  annual_returns: AnnualReturn[]
  monthly_returns: MonthlyReturn[]
}

/* ============================================================
 * Stress tests
 * ============================================================ */

export interface StressCurvePoint {
  date: string
  value: number
}

export interface StressScenario {
  name: string
  start_date: string
  end_date: string
  spy_return_pct: number
  portfolio_simulated_return_pct: number
  spy_curve: StressCurvePoint[]
  portfolio_curve: StressCurvePoint[]
}

export interface StressTestPayload {
  scenarios: StressScenario[]
  message?: string
}

/* ============================================================
 * Trade journal
 * ============================================================ */

export interface TradeJournalEntry {
  id: number
  trade_id: string
  strategy_id: string
  strategy_name?: string | null
  symbol: string
  entry_time: string
  entry_price: number
  entry_size: number
  entry_reason: string
  exit_time?: string | null
  exit_price?: number | null
  exit_reason?: string | null
  pnl?: number | null
  pnl_percent?: number | null
  hold_time_hours?: number | null
  max_adverse_excursion?: number | null
  max_favorable_excursion?: number | null
  entry_slippage?: number | null
  exit_slippage?: number | null
  market_regime?: string | null
  sector?: string | null
  conviction_score?: number | null
  ml_confidence?: number | null
}

export interface TradeJournalPayload {
  trades: TradeJournalEntry[]
  total_count: number
}

export interface TradeJournalPatternsPayload {
  best_patterns: Array<Record<string, unknown>>
  worst_patterns: Array<Record<string, unknown>>
  recommendations: Array<Record<string, unknown>>
}

/* ============================================================
 * Hooks — one per endpoint. Two-minute poll on cold analytics,
 * five-minute staleTime on cross-cutting queries like SPY.
 * ============================================================ */

export function useAnalyticsPerformance(period: ResearchPeriod, interval: ResearchInterval) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<PerformanceAnalyticsPayload>({
    queryKey: ['analytics-performance', mode, period, interval],
    queryFn: () =>
      api.get<PerformanceAnalyticsPayload>('/analytics/performance', {
        mode,
        period,
        interval,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useSpyBenchmark(period: ResearchPeriod, enabled = true) {
  return useQuery<SpyBenchmarkPayload>({
    queryKey: ['spy-benchmark', period],
    queryFn: () => api.get<SpyBenchmarkPayload>('/analytics/spy-benchmark', { period }),
    enabled,
    staleTime: 5 * 60_000,
  })
}

export function useStrategyAttribution(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<StrategyAttribution[]>({
    queryKey: ['strategy-attribution', mode, period],
    queryFn: () =>
      api.get<StrategyAttribution[]>('/analytics/strategy-attribution', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function usePerformanceAttribution(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<PerformanceAttributionPayload>({
    queryKey: ['performance-attribution', mode, period],
    queryFn: () =>
      api.get<PerformanceAttributionPayload>('/analytics/performance-attribution', {
        mode,
        period,
        group_by: 'sector',
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useTradeAnalytics(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TradeAnalyticsPayload>({
    queryKey: ['trade-analytics', mode, period],
    queryFn: () =>
      api.get<TradeAnalyticsPayload>('/analytics/trade-analytics', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useRollingStatistics(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<RollingStatsPayload>({
    queryKey: ['rolling-statistics', mode, period],
    queryFn: () =>
      api.get<RollingStatsPayload>('/analytics/rolling-statistics', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function usePerformanceStats() {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<PerformanceStatsPayload>({
    queryKey: ['performance-stats', mode],
    queryFn: () => api.get<PerformanceStatsPayload>('/analytics/performance-stats', { mode }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

/* ───── Sprint 11 ───── */

export function useRegimeComprehensive() {
  return useQuery<RegimeComprehensivePayload>({
    queryKey: ['regime-comprehensive'],
    queryFn: () => api.get<RegimeComprehensivePayload>('/analytics/regime-comprehensive'),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useFundamentalStats(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<FundamentalStats>({
    queryKey: ['alpha-edge-fundamental-stats', mode, period],
    queryFn: () =>
      api.get<FundamentalStats>('/analytics/alpha-edge/fundamental-stats', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useMLStats(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<MLStats>({
    queryKey: ['alpha-edge-ml-stats', mode, period],
    queryFn: () =>
      api.get<MLStats>('/analytics/alpha-edge/ml-stats', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useConvictionDistribution(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<ConvictionDistributionPayload>({
    queryKey: ['alpha-edge-conviction-distribution', mode, period],
    queryFn: () =>
      api.get<ConvictionDistributionPayload>(
        '/analytics/alpha-edge/conviction-distribution',
        { mode, period },
      ),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useTemplatePerformance(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TemplatePerformance[]>({
    queryKey: ['alpha-edge-template-performance', mode, period],
    queryFn: () =>
      api.get<TemplatePerformance[]>(
        '/analytics/alpha-edge/template-performance',
        { mode, period },
      ),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useTransactionCostSavings(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TransactionCostSavings>({
    queryKey: ['alpha-edge-tcs', mode, period],
    queryFn: () =>
      api.get<TransactionCostSavings>(
        '/analytics/alpha-edge/transaction-cost-savings',
        { mode, period },
      ),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useTearSheet(period: ResearchPeriod) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TearSheetPayload>({
    queryKey: ['tear-sheet', mode, period],
    queryFn: () =>
      api.get<TearSheetPayload>('/analytics/tear-sheet', {
        mode,
        period,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useStressTests() {
  return useQuery<StressTestPayload>({
    queryKey: ['stress-tests'],
    queryFn: () => api.get<StressTestPayload>('/analytics/stress-tests'),
    refetchInterval: 300_000,
    staleTime: 5 * 60_000,
  })
}

export interface TradeJournalFilters {
  strategyId?: string | null
  symbol?: string | null
  startDate?: string | null
  endDate?: string | null
  minPnl?: number | null
  maxPnl?: number | null
  regime?: string | null
  sector?: string | null
  limit?: number
  offset?: number
}

export function useTradeJournal(filters: TradeJournalFilters = {}) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TradeJournalPayload>({
    queryKey: ['trade-journal', mode, filters],
    queryFn: () =>
      api.get<TradeJournalPayload>('/analytics/trade-journal', {
        strategy_id: filters.strategyId ?? undefined,
        symbol: filters.symbol ?? undefined,
        start_date: filters.startDate ?? undefined,
        end_date: filters.endDate ?? undefined,
        min_pnl: filters.minPnl ?? undefined,
        max_pnl: filters.maxPnl ?? undefined,
        regime: filters.regime ?? undefined,
        sector: filters.sector ?? undefined,
        limit: filters.limit ?? 200,
        offset: filters.offset ?? 0,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useTradeJournalPatterns() {
  return useQuery<TradeJournalPatternsPayload>({
    queryKey: ['trade-journal-patterns'],
    queryFn: () =>
      api.get<TradeJournalPatternsPayload>('/analytics/trade-journal/patterns'),
    refetchInterval: 300_000,
    staleTime: 5 * 60_000,
  })
}

/* Export URL builder for journal CSV download. Avoids blob churn. */
export function buildTradeJournalExportUrl(filters: TradeJournalFilters): string {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const params = new URLSearchParams()
  if (filters.strategyId) params.set('strategy_id', filters.strategyId)
  if (filters.symbol) params.set('symbol', filters.symbol)
  if (filters.startDate) params.set('start_date', filters.startDate)
  if (filters.endDate) params.set('end_date', filters.endDate)
  if (filters.regime) params.set('regime', filters.regime)
  if (filters.sector) params.set('sector', filters.sector)
  const qs = params.toString()
  return `${base}/analytics/trade-journal/export${qs ? `?${qs}` : ''}`
}
