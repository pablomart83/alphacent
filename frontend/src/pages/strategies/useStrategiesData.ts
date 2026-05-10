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


/* ═════════════════════════════════════════════════════════════════════
 *  Cycle data hooks — Sprint 6
 * ═════════════════════════════════════════════════════════════════════ */

export type SystemStateValue = 'ACTIVE' | 'PAUSED' | 'STOPPED' | 'EMERGENCY_HALT'

export interface SystemStatusPayload {
  state: SystemStateValue
  timestamp: string
  active_strategies: number
  open_positions: number
  reason: string
  uptime_seconds: number
  last_signal_generated?: string | null
  last_order_executed?: string | null
}

export interface ScheduleSlot {
  id: string
  enabled: boolean
  /** lowercase day names: monday..sunday */
  days: string[]
  hour: number
  minute: number
}

export interface SchedulesPayload {
  success: boolean
  schedules: ScheduleSlot[]
  next_runs: Array<string | null>
  last_run: string | null
  message: string
}

export interface CycleRunRow {
  id: number
  cycle_id: string
  status: 'running' | 'completed' | 'error' | string
  started_at: string
  completed_at: string | null
  duration_seconds: number | null
  strategies_cleaned: number
  strategies_retired: number
  trades_analyzed: number
  template_adjustments: number
  proposals_generated: number
  proposals_pre_wf: number
  proposals_alpha_edge: number
  proposals_template: number
  symbols_checked: number
  symbols_passed: number
  symbols_failed: number
  backtested: number
  backtest_passed: number
  backtest_failed: number
  avg_sharpe: number | null
  avg_win_rate: number | null
  activated: number
  promoted_to_paper: number
  total_active: number
  total_backtested: number
  signals_generated: number
  signals_passed: number
  orders_submitted: number
  orders_filled: number
  orders_pending: number
  orders_rejected: number
  stage_details: Record<string, unknown> | null
  errors: unknown[] | null
}

export interface CyclesPayload {
  success: boolean
  data: CycleRunRow[]
  error?: string
}

export interface FunnelStage {
  stage: string
  count: number
  drop_from_prev: number | null
}

export interface FunnelPayload {
  lookback_days: number
  funnel: FunnelStage[]
  error?: string
}

export interface TriggerCycleBody {
  force?: boolean
  asset_classes?: string[]
  intervals?: string[]
  strategy_types?: string[]
}

export interface TriggerCycleResponse {
  success: boolean
  message: string
  cycle_id?: string
  estimated_duration?: number
}

/* ──── Queries ──── */

export function useSystemStatus(enabled = true) {
  return useQuery<SystemStatusPayload>({
    queryKey: ['system-status'],
    queryFn: () => api.get<SystemStatusPayload>('/control/system/status'),
    refetchInterval: 15_000,
    staleTime: 5_000,
    enabled,
  })
}

export function useAutonomousSchedules() {
  return useQuery<SchedulesPayload>({
    queryKey: ['autonomous-schedules'],
    queryFn: () => api.get<SchedulesPayload>('/control/autonomous/schedules'),
    staleTime: 60_000,
  })
}

export function useAutonomousCycles(limit = 30) {
  return useQuery<CyclesPayload>({
    queryKey: ['autonomous-cycles', { limit }],
    queryFn: () => api.get<CyclesPayload>('/control/autonomous/cycles', { limit }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useGraduationFunnel(lookbackDays = 30) {
  return useQuery<FunnelPayload>({
    queryKey: ['graduation-funnel', lookbackDays],
    queryFn: () =>
      api.get<FunnelPayload>('/analytics/observability/graduation-funnel', {
        lookback_days: lookbackDays,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

/* ──── Mutations ──── */

export function useUpdateSchedules() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (schedules: ScheduleSlot[]) =>
      api.post<SchedulesPayload>('/control/autonomous/schedules', {
        schedules,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autonomous-schedules'] })
      qc.invalidateQueries({ queryKey: ['autonomous-status'] })
    },
  })
}

export function useTriggerCycle() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: TriggerCycleBody) =>
      api.post<TriggerCycleResponse>('/strategies/autonomous/trigger', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['autonomous-cycles'] })
      qc.invalidateQueries({ queryKey: ['autonomous-status'] })
      qc.invalidateQueries({ queryKey: ['system-status'] })
    },
  })
}

/* System-state transitions — every call takes `{ confirmation: true }`. */
type SystemAction = 'start' | 'pause' | 'stop' | 'resume' | 'reset'

export function useSystemStateTransition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ action }: { action: SystemAction }) =>
      api.post<{ success: boolean; message: string; state: SystemStateValue }>(
        `/control/system/${action}`,
        { confirmation: true },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-status'] })
      qc.invalidateQueries({ queryKey: ['autonomous-status'] })
    },
  })
}

/* ──── Valid transition map — matches backend system_state_manager ──── */
export function validTransitions(state: SystemStateValue | undefined): SystemAction[] {
  switch (state) {
    case 'ACTIVE':
      return ['pause', 'stop']
    case 'PAUSED':
      return ['resume', 'stop']
    case 'STOPPED':
      return ['start']
    case 'EMERGENCY_HALT':
      return ['reset']
    default:
      return ['start']
  }
}

/* ──── Stage name normalisation ─────────────────────────────────────────
 *  Backend WS events use implementation stage keys
 *  (cleanup_retirement, strategy_proposals, walk_forward_backtesting, ...).
 *  The spec describes the cycle as 9 business-logic stages. Map the
 *  backend keys onto the spec stage ids so the pipeline visual is
 *  consistent across WS pushes and DB summaries.
 *
 *  Spec stages (in order):
 *    cleanup → market_analysis → proposal → walk_forward → monte_carlo →
 *    direction_aware → conviction → activation → signal_generation
 * ─────────────────────────────────────────────────────────────────────── */

export type SpecStageId =
  | 'cleanup'
  | 'market_analysis'
  | 'proposal'
  | 'walk_forward'
  | 'monte_carlo'
  | 'direction_aware'
  | 'conviction'
  | 'activation'
  | 'signal_generation'

export const SPEC_STAGES: Array<{ id: SpecStageId; label: string }> = [
  { id: 'cleanup', label: 'Cleanup' },
  { id: 'market_analysis', label: 'Market analysis' },
  { id: 'proposal', label: 'Proposal' },
  { id: 'walk_forward', label: 'Walk-forward' },
  { id: 'monte_carlo', label: 'Monte Carlo' },
  { id: 'direction_aware', label: 'Direction-aware' },
  { id: 'conviction', label: 'Conviction' },
  { id: 'activation', label: 'Activation' },
  { id: 'signal_generation', label: 'Signal generation' },
]

/**
 * Map a backend stage key (from WS `cycle_progress` or from
 * CycleRunRow.stage_details keys) to the corresponding spec stage id.
 */
export function mapBackendStageToSpec(backendStage: string): SpecStageId | null {
  const key = backendStage.toLowerCase()
  switch (key) {
    case 'cleanup_retirement':
    case 'cleanup':
      return 'cleanup'
    case 'performance_feedback':
    case 'market_analysis':
    case 'regime_detection':
    case 'data_validation':
    case 'cache_warming':
      return 'market_analysis'
    case 'strategy_proposals':
    case 'proposal':
      return 'proposal'
    case 'walk_forward_backtesting':
    case 'walk_forward':
    case 'backtesting':
      return 'walk_forward'
    case 'monte_carlo':
    case 'bootstrap':
      return 'monte_carlo'
    case 'direction_aware':
    case 'direction_aware_thresholds':
      return 'direction_aware'
    case 'conviction':
    case 'conviction_scoring':
      return 'conviction'
    case 'strategy_activation':
    case 'activation':
      return 'activation'
    case 'signal_generation':
    case 'order_submission':
    case 'signals':
      return 'signal_generation'
    default:
      return null
  }
}
