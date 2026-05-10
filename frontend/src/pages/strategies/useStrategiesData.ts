import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode, type TradingMode } from '@/stores'

/* ═════════════════════════════════════════════════════════════════════
 *  Response shapes (mirror the backend Pydantic models in
 *  src/api/routers/strategies.py). Kept narrow — only the fields the UI
 *  actually consumes. The full payload still round-trips through the
 *  network, we're just being explicit about what we rely on.
 * ═════════════════════════════════════════════════════════════════════ */

export type StrategyStatus = 'PROPOSED' | 'BACKTESTED' | 'PAPER' | 'LIVE' | 'RETIRED' | 'DEMO'

export interface PerformanceMetrics {
  total_return: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  avg_win: number
  avg_loss: number
  total_trades: number
  live_orders?: number
  open_positions?: number
  unrealized_pnl?: number
  total_pnl?: number | null
  health_score?: number | null
  decay_score?: number | null
}

export interface WalkForwardResults {
  train_sharpe?: number | null
  test_sharpe?: number | null
  train_return?: number | null
  test_return?: number | null
  train_max_drawdown?: number | null
  test_max_drawdown?: number | null
  train_win_rate?: number | null
  test_win_rate?: number | null
  train_trades?: number | null
  test_trades?: number | null
  consistency_score?: number | null
  /** Monte Carlo / bootstrap percentiles on final equity or Sharpe. */
  bootstrap?: {
    p5?: number | null
    p50?: number | null
    p95?: number | null
    samples?: number | null
  } | null
  /** Per-trade P&L from the backtest — used for regime distribution. */
  trades?: Array<{
    symbol?: string | null
    regime?: string | null
    pnl?: number | null
    entry_timestamp?: string | null
    exit_timestamp?: string | null
  }> | null
  /** Optional equity curve from the WF run. */
  equity_curve?: Array<{ date: string; equity: number }> | null
  [key: string]: unknown
}

export interface StrategyReasoning {
  hypothesis?: string | null
  alpha_sources?: Array<{ source: string; weight?: number | null } | string> | null
  market_assumptions?: string[] | null
  signal_logic?: string | null
  [key: string]: unknown
}

export interface StrategyMetadata {
  template_name?: string | null
  strategy_category?: string | null
  market_regime?: string | null
  activation_regime?: string | null
  interval?: string | null
  direction?: string | null
  health_score?: number | null
  decay_score?: number | null
  conviction_score?: number | null
  conviction_score_breakdown?: {
    wf_edge?: number | null
    signal_quality?: number | null
    regime_fit?: number | null
    asset_tradability?: number | null
    fundamental?: number | null
    carry?: number | null
    crypto_cycle?: number | null
    sentiment?: number | null
    factor?: number | null
  } | null
  wf_test_sharpe?: number | null
  /** Live performance — populated for LIVE strategies only. */
  live_pnl?: number | null
  live_trades?: number | null
  source?: string | null
  asset_class?: string | null
  last_signal_at?: string | null
  last_fill_at?: string | null
  [key: string]: unknown
}

export interface StrategyRow {
  id: string
  name: string
  description: string
  status: StrategyStatus
  rules: Record<string, unknown>
  symbols: string[]
  allocation_percent: number
  risk_params: Record<string, number>
  created_at: string
  activated_at?: string | null
  retired_at?: string | null
  performance_metrics: PerformanceMetrics
  reasoning?: StrategyReasoning | null
  updated_at?: string | null
  source?: string | null
  template_name?: string | null
  market_regime?: string | null
  entry_rules?: string[] | null
  exit_rules?: string[] | null
  walk_forward_results?: WalkForwardResults | null
  metadata?: StrategyMetadata | null
  strategy_category?: string | null
  strategy_type?: string | null
  requires_fundamental_data?: boolean | null
  requires_earnings_data?: boolean | null
  traded_symbols?: string[] | null
  alpha_vs_spy?: number | null
  deployed_capital?: number | null
  allocated_capital?: number | null
}

export interface StrategiesPayload {
  strategies: StrategyRow[]
  total_count: number
}

export interface BacktestResultsPayload {
  strategy_id: string
  total_return: number
  sharpe_ratio: number
  sortino_ratio: number
  max_drawdown: number
  win_rate: number
  avg_win: number
  avg_loss: number
  total_trades: number
  backtest_period: { start: string; end: string }
  gross_return?: number
  net_return?: number
  total_transaction_costs?: number
  transaction_costs_pct?: number
  message?: string
}

export interface StrategyActionResponse {
  success: boolean
  message: string
  strategy_id: string
}

export interface GraduateBody {
  symbol: string
  position_size: number
  sl_pct: number
  tp_pct: number
  conviction_min?: number
  notes?: string
}

export interface RejectGraduationBody {
  symbol: string
  notes?: string
}

/* ═════════════════════════════════════════════════════════════════════
 *  Queries
 * ═════════════════════════════════════════════════════════════════════ */

function useMode(pin?: TradingMode): TradingMode {
  const active = useTradingMode((s) => s.mode)
  return pin ?? active
}

export interface UseStrategiesOptions {
  /** Slim payload for list views (no rules/reasoning/WF/SPY). Default: true. */
  slim?: boolean
  /** Whether to include retired strategies. Default: true — library needs them. */
  include_retired?: boolean
  status_filter?: StrategyStatus
  pinMode?: TradingMode
  /** Pass `false` to freeze the query (e.g. when the surface isn't mounted). */
  enabled?: boolean
}

/**
 * Library table payload. Defaults match the spec: slim + include_retired, which
 * gives the 50 PAPER + 74 BACKTESTED + retired history in ~8KB.
 */
export function useStrategies(opts: UseStrategiesOptions = {}) {
  const { slim = true, include_retired = true, status_filter, pinMode, enabled = true } = opts
  const mode = useMode(pinMode)
  return useQuery<StrategiesPayload>({
    queryKey: ['strategies', mode, { slim, include_retired, status_filter: status_filter ?? null }],
    queryFn: () =>
      api.get<StrategiesPayload>('/strategies', {
        mode,
        slim,
        include_retired,
        status_filter,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
    enabled,
  })
}

/**
 * Full strategy detail (with rules, reasoning, walk_forward_results). Only
 * fetched when a row is selected in the detail panel.
 */
export function useStrategy(strategyId: string | null, pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<StrategyRow>({
    queryKey: ['strategy', strategyId, mode],
    queryFn: () =>
      api.get<StrategyRow>(`/strategies/${strategyId}`, { mode }),
    enabled: !!strategyId,
    staleTime: 30_000,
  })
}

/* ═════════════════════════════════════════════════════════════════════
 *  Mutations
 * ═════════════════════════════════════════════════════════════════════ */

function invalidateLibrary(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['strategies'] })
  qc.invalidateQueries({ queryKey: ['dashboard'] })
}

export function useActivateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      strategyId,
      mode,
      allocation_percent = 5.0,
    }: {
      strategyId: string
      mode: TradingMode
      allocation_percent?: number
    }) =>
      api.post<StrategyActionResponse>(
        `/strategies/${strategyId}/activate`,
        undefined,
        { mode, allocation_percent },
      ),
    onSuccess: (_d, vars) => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['strategy', vars.strategyId] })
    },
  })
}

export function useDeactivateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ strategyId, mode }: { strategyId: string; mode: TradingMode }) =>
      api.post<StrategyActionResponse>(
        `/strategies/${strategyId}/deactivate`,
        undefined,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['strategy', vars.strategyId] })
    },
  })
}

/** Retire + delete from DB (single action per the backend endpoint). */
export function useRetireStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ strategyId, mode }: { strategyId: string; mode: TradingMode }) =>
      api.delete<StrategyActionResponse>(`/strategies/${strategyId}`, { mode }),
    onSuccess: (_d, vars) => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['strategy', vars.strategyId] })
    },
  })
}

/** Permanent delete — only valid for RETIRED strategies. */
export function useDeleteStrategyPermanent() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ strategyId, mode }: { strategyId: string; mode: TradingMode }) =>
      api.delete<StrategyActionResponse>(
        `/strategies/${strategyId}/permanent`,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['strategy', vars.strategyId] })
    },
  })
}

/** Kicks off a backtest run. Backend persists results to the strategy record. */
export function useStrategyBacktest() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      strategyId,
      start_date,
      end_date,
    }: {
      strategyId: string
      start_date?: string
      end_date?: string
    }) =>
      api.post<BacktestResultsPayload>(`/strategies/${strategyId}/backtest`, {
        start_date,
        end_date,
      }),
    onSuccess: (_d, vars) => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['strategy', vars.strategyId] })
    },
  })
}

/** Approve a (template, symbol) pair for live trading. */
export function useGraduateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      strategyId,
      body,
    }: {
      strategyId: string
      body: GraduateBody
    }) =>
      api.post<{ success: boolean; live_strategy: Record<string, unknown> }>(
        `/strategies/${strategyId}/graduate`,
        body,
      ),
    onSuccess: () => {
      invalidateLibrary(qc)
      qc.invalidateQueries({ queryKey: ['graduation-queue'] })
      qc.invalidateQueries({ queryKey: ['live-strategies'] })
      qc.invalidateQueries({ queryKey: ['live-divergence'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
    },
  })
}

export function useRejectGraduation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      strategyId,
      body,
    }: {
      strategyId: string
      body: RejectGraduationBody
    }) =>
      api.post<{ success: boolean; rejection: Record<string, unknown> }>(
        `/strategies/${strategyId}/reject-graduation`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['graduation-queue'] })
    },
  })
}

/* ═════════════════════════════════════════════════════════════════════
 *  Derived helpers
 * ═════════════════════════════════════════════════════════════════════ */

/** Paper-eligible: PAPER status with >= 20 trades. */
export function isGraduationEligible(s: StrategyRow): boolean {
  if (s.status !== 'PAPER') return false
  const trades = s.performance_metrics?.total_trades ?? 0
  const sharpe = s.performance_metrics?.sharpe_ratio ?? 0
  return trades >= 20 && sharpe >= 1.0
}

/** Idle if last signal / fill is more than 7 days old. */
export function isIdle7d(s: StrategyRow): boolean {
  const ts = s.metadata?.last_signal_at || s.metadata?.last_fill_at
  if (!ts) return false
  const age = Date.now() - new Date(ts.endsWith('Z') ? ts : `${ts}Z`).getTime()
  return age > 7 * 86_400_000
}

/** Signals-firing-today uses last_signal_at ≤ 24h. */
export function hasSignalToday(s: StrategyRow): boolean {
  const ts = s.metadata?.last_signal_at
  if (!ts) return false
  const age = Date.now() - new Date(ts.endsWith('Z') ? ts : `${ts}Z`).getTime()
  return age <= 86_400_000
}

/** Negative live P&L — only meaningful for LIVE-authorized strategies. */
export function hasNegativeLivePnl(s: StrategyRow): boolean {
  const livePnl = s.metadata?.live_pnl
  return typeof livePnl === 'number' && livePnl < 0
}

export function hasPaper20Plus(s: StrategyRow): boolean {
  if (s.status !== 'PAPER') return false
  return (s.performance_metrics?.total_trades ?? 0) >= 20
}
