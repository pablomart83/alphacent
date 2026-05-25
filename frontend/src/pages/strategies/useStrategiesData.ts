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
  /** Set when synthesized from strategy_metadata (autonomous strategies). */
  walk_forward_validated?: boolean | null
  performance_degradation?: number | null
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
  live_today?: boolean | null
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
  /** True when this strategy has an active live_strategies authorization row. */
  is_live_authorized?: boolean | null
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

/** Promoted Today — pre-existing strategy promoted to PAPER today (activated_at today, created_at not today). */
export function isPromotedToday(s: StrategyRow): boolean {
  if (!s.activated_at) return false
  const today = new Date().toISOString().slice(0, 10)
  const activatedDay = s.activated_at.slice(0, 10)
  const createdDay = s.created_at?.slice(0, 10)
  return activatedDay === today && createdDay !== today
}

/** Activated Today — brand-new strategy created today. */
export function isActivatedToday(s: StrategyRow): boolean {
  if (!s.created_at) return false
  const today = new Date().toISOString().slice(0, 10)
  return s.created_at.slice(0, 10) === today
}

/** Live Today — strategy that graduated to live trading today. */
export function isLiveToday(s: StrategyRow): boolean {
  return s.metadata?.live_today === true
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
    refetchInterval: 30_000,
    staleTime: 15_000,
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
    // Poll faster while a cycle might be running — the WS events are the
    // primary update path but DB polling catches any missed events.
    refetchInterval: (query) => {
      const rows = (query.state.data as CyclesPayload | undefined)?.data ?? []
      const isRunning = rows.some((r) => r.status?.toLowerCase() === 'running')
      return isRunning ? 5_000 : 60_000
    },
    staleTime: 5_000,
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
    case 'cache_warming':
      return 'market_analysis'
    // data_validation validates the proposals list — it belongs in the proposal stage
    case 'data_validation':
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

/* ═════════════════════════════════════════════════════════════════════
 *  Sprint 7 — Templates, Symbols, Graduation, Lab data hooks
 * ═════════════════════════════════════════════════════════════════════ */

/* ──── Template types ──── */

export interface TemplateRow {
  name: string
  description: string
  market_regimes: string[]
  indicators: string[]
  entry_rules: string[]
  exit_rules: string[]
  success_rate: number
  usage_count: number
  strategy_type?: string | null
  direction?: string | null
  asset_classes: string[]
  expected_trade_frequency?: string | null
  expected_holding_period?: string | null
  risk_reward_ratio?: number | null
  enabled: boolean
  active_strategies: number
  total_strategies_ever: number
  avg_sharpe?: number | null
  avg_win_rate?: number | null
  avg_return?: number | null
  total_trades_live: number
  total_pnl?: number | null
  best_symbol?: string | null
  worst_symbol?: string | null
  last_proposed?: string | null
  last_activated?: string | null
  is_intraday: boolean
  is_4h: boolean
  interval: '1d' | '4h' | '1h' | string
  activated_count: number
  traded_count: number
  proposed_count: number
  approved_count: number
  strategy_category?: string | null
}

export interface TemplatesListPayload {
  templates: TemplateRow[]
  total: number
}

export interface TemplateRankingRow {
  name: string
  win_rate?: number | null
  avg_sharpe?: number | null
  total_trades: number
  active_count: number
  last_proposal_date?: string | null
}

export interface TemplateRankingsPayload {
  rankings: TemplateRankingRow[]
  total: number
}

/* ──── Symbol types ──── */

export interface SymbolStatsRow {
  symbol: string
  asset_class: string
  sector: string
  active_strategies: number
  activated_count: number
  traded_count: number
  usage_count: number
  proposed_count: number
  approved_count: number
  avg_sharpe?: number | null
  avg_win_rate?: number | null
  total_pnl?: number | null
  total_trades_live: number
  open_positions: number
  best_template?: string | null
  worst_template?: string | null
  last_signal?: string | null
  last_trade?: string | null
}

export interface SymbolsListPayload {
  symbols: SymbolStatsRow[]
  total: number
}

export interface BlacklistEntry {
  template: string
  symbol: string
  count: number
  timestamp: string
  type: string
}

export interface BlacklistPayload {
  entries: BlacklistEntry[]
  total: number
}

export interface IdleDemotionEntry {
  name: string
  strategy_id: string
  timestamp: string
  reason: string
}

export interface IdleDemotionsPayload {
  entries: IdleDemotionEntry[]
  total: number
}

/* ──── Graduation types ──── */

export interface GraduationQueueRow {
  strategy_id: string
  strategy_name: string
  template_name?: string | null
  symbol: string
  paper_trades: number
  paper_sharpe?: number | null
  paper_win_rate?: number | null
  paper_total_pnl?: number | null
  avg_paper_pnl_per_trade?: number | null
  wf_sharpe?: number | null
  qualification_ratio?: number | null
  strategy_interval?: string | null
  strategy_versions?: number | null
  first_paper_trade?: string | null
}

export interface GraduationQueuePayload {
  queue: GraduationQueueRow[]
  count: number
}

export interface LiveStrategyRow {
  id: number
  graduation_id?: number | null
  strategy_id: string
  template_name?: string | null
  symbol: string
  activated_at: string
  retired_at?: string | null
  retirement_reason?: string | null
  position_size?: number | null
  sl_pct?: number | null
  tp_pct?: number | null
  conviction_min?: number | null
  live_trades?: number | null
  live_pnl?: number | null
  live_sharpe?: number | null
  current_paper_sharpe?: number | null
  current_paper_win_rate?: number | null
  current_paper_pnl?: number | null
  current_paper_trades?: number | null
  divergence_pct?: number | null
  // Open position fields — populated even before first trade closes
  open_position_count?: number | null
  unrealized_pnl?: number | null
  open_position_entry?: number | null
  open_position_current?: number | null
  // Last signal cycle outcome
  last_signal_status?: string | null
  last_signal_detail?: string | null
  pending_order?: {
    order_id: string
    etoro_order_id?: string | null
    submitted_at?: string | null
    quantity?: number | null
    etoro_status?: string | null
    etoro_units?: number | null
    etoro_amount?: number | null
    age_mins?: number | null
  } | null
  // Live trade breakdown (from trade_journal)
  live_closed_trades?: number | null
  live_open_trades?: number | null
  live_realized_pnl?: number | null
  live_win_rate?: number | null
  live_avg_pnl?: number | null
  live_best_trade?: number | null
  live_worst_trade?: number | null
  live_avg_hold_hours?: number | null
  live_last_opened?: string | null
  live_last_closed?: string | null
  live_trade_history?: Array<{
    id: string
    entry_price?: number | null
    exit_price?: number | null
    pnl?: number | null
    pnl_percent?: number | null
    entry_time?: string | null
    exit_time?: string | null
    hold_time_hours?: number | null
    exit_reason?: string | null
    is_open: boolean
  }> | null
}

export interface LiveStrategiesPayload {
  live_strategies: LiveStrategyRow[]
  count: number
}

/* ──── Lab types ──── */

export interface VibeCodePayload {
  action: string
  symbol: string
  quantity?: number | null
  price?: number | null
  reason: string
  translated_from: string
}

export interface BootstrapStrategyInfo {
  id: string
  name: string
  description: string
  status: StrategyStatus
  symbols: string[]
  allocation_percent: number
  backtest_results?: {
    total_return: number
    sharpe_ratio: number
    sortino_ratio: number
    max_drawdown: number
    win_rate: number
    total_trades: number
  } | null
}

export interface BootstrapPayload {
  success: boolean
  message: string
  strategies: BootstrapStrategyInfo[]
  summary: {
    total_generated?: number
    total_backtested?: number
    total_activated?: number
    errors?: unknown[]
    [key: string]: unknown
  }
}

/* ──── Queries ──── */

export function useTemplates(marketRegime?: string | null) {
  return useQuery<TemplatesListPayload>({
    queryKey: ['strategy-templates', marketRegime ?? 'all'],
    queryFn: () =>
      api.get<TemplatesListPayload>('/strategies/templates', {
        market_regime: marketRegime || undefined,
      }),
    staleTime: 60_000,
    refetchInterval: 120_000,
  })
}

export function useTemplateRankings(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<TemplateRankingsPayload>({
    queryKey: ['template-rankings', mode],
    queryFn: () =>
      api.get<TemplateRankingsPayload>('/strategies/template-rankings', {
        mode,
      }),
    staleTime: 60_000,
  })
}

export function useSymbolStats() {
  return useQuery<SymbolsListPayload>({
    queryKey: ['symbol-stats'],
    queryFn: () => api.get<SymbolsListPayload>('/strategies/symbols'),
    staleTime: 60_000,
  })
}

export function useBlacklistedCombos() {
  return useQuery<BlacklistPayload>({
    queryKey: ['blacklisted-combos'],
    queryFn: () => api.get<BlacklistPayload>('/strategies/blacklisted-combos'),
    staleTime: 120_000,
  })
}

export function useIdleDemotions() {
  return useQuery<IdleDemotionsPayload>({
    queryKey: ['idle-demotions'],
    queryFn: () => api.get<IdleDemotionsPayload>('/strategies/idle-demotions'),
    staleTime: 120_000,
  })
}

export function useGraduationQueue() {
  return useQuery<GraduationQueuePayload>({
    queryKey: ['graduation-queue'],
    queryFn: () => api.get<GraduationQueuePayload>('/strategies/graduation-queue'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

/* ── Approaching graduation ── */

export interface ApproachingGraduationRow {
  template_name: string
  symbol: string
  trades: number
  sharpe: number
  win_rate: number
  total_pnl: number
  wf_sharpe: number | null
  qualification_ratio: number | null
  strategy_versions: number
  first_trade: string | null
  last_trade: string | null
  graduation_score: number
  missing_criteria: string[]
  progress: {
    trades: number
    sharpe: number
    win_rate: number
    pnl: number
  }
}

export interface ApproachingGraduationPayload {
  approaching: ApproachingGraduationRow[]
  count: number
}

export function useApproachingGraduation(minTrades = 5, limit = 20) {
  return useQuery<ApproachingGraduationPayload>({
    queryKey: ['approaching-graduation', minTrades, limit],
    queryFn: () =>
      api.get<ApproachingGraduationPayload>('/strategies/approaching-graduation', {
        min_trades: minTrades,
        limit,
      }),
    refetchInterval: 120_000,
    staleTime: 60_000,
  })
}

export function useLiveStrategies() {
  return useQuery<LiveStrategiesPayload>({
    queryKey: ['live-strategies'],
    queryFn: () => api.get<LiveStrategiesPayload>('/strategies/live'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export interface UpdateLiveStrategyBody {
  position_size?: number
  sl_pct?: number
  tp_pct?: number
  conviction_min?: number
}

export function useUpdateLiveStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ liveId, body }: { liveId: number; body: UpdateLiveStrategyBody }) =>
      api.patch<{ success: boolean; message: string; live_id: number }>(
        `/live/strategies/${liveId}`,
        body,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-strategies'] })
      qc.invalidateQueries({ queryKey: ['live-divergence'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
    },
  })
}

/* ──── Mutations ──── */

export function useToggleTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ name, enabled }: { name: string; enabled: boolean }) =>
      api.put<StrategyActionResponse>(
        `/strategies/templates/${encodeURIComponent(name)}/toggle`,
        { enabled },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategy-templates'] })
      qc.invalidateQueries({ queryKey: ['template-rankings'] })
    },
  })
}

export function useBulkToggleTemplates() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      names,
      enabled,
    }: {
      names: string[]
      enabled: boolean
    }) =>
      api.put<StrategyActionResponse>('/strategies/templates/bulk-toggle', {
        template_names: names,
        enabled,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategy-templates'] })
      qc.invalidateQueries({ queryKey: ['template-rankings'] })
    },
  })
}

/* Retire a LIVE authorisation — same endpoint the Book / Live surface uses.
 * Mirrored here for the Graduation tab's ActiveLiveTable. */
export function useRetireLiveStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ liveId }: { liveId: number }) =>
      api.post<{ success: boolean; retired_at: string }>(
        `/live/strategies/${liveId}/retire`,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-strategies'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
      qc.invalidateQueries({ queryKey: ['live-divergence'] })
      qc.invalidateQueries({ queryKey: ['graduation-queue'] })
    },
  })
}

/* Lab — vibe code / generate / bootstrap.
 * LLM endpoints can be slow (20-60s). We don't add refetchInterval. */

export function useVibeCodeTranslate() {
  return useMutation({
    mutationFn: async ({ naturalLanguage }: { naturalLanguage: string }) =>
      api.post<VibeCodePayload>('/strategies/vibe-code/translate', {
        natural_language: naturalLanguage,
      }),
  })
}

export function useGenerateStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      prompt,
      constraints = {},
    }: {
      prompt: string
      constraints?: Record<string, unknown>
    }) =>
      api.post<StrategyRow>('/strategies/generate', {
        prompt,
        constraints,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
    },
  })
}

export function useBootstrap() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      strategy_types,
      auto_activate = false,
      min_sharpe = 1.0,
      backtest_days = 90,
    }: {
      strategy_types?: string[]
      auto_activate?: boolean
      min_sharpe?: number
      backtest_days?: number
    }) =>
      api.post<BootstrapPayload>('/strategies/bootstrap', {
        strategy_types,
        auto_activate,
        min_sharpe,
        backtest_days,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['strategies'] })
      qc.invalidateQueries({ queryKey: ['strategy-templates'] })
    },
  })
}

/* ──── Derived helpers ──── */

/** LIVE conviction threshold lookup — spec §3A / autonomous_trading.yaml. */
export function liveConvictionThresholdFor(assetClass?: string | null): number {
  const c = (assetClass ?? '').toLowerCase()
  if (c === 'crypto') return 68
  return 74
}

/** Crypto / equity symbol detection from asset_class or symbol pattern. */
export function assetClassForSymbol(symbol: string, explicit?: string | null): string {
  if (explicit && explicit !== 'unknown') return explicit.toLowerCase()
  const s = symbol.toUpperCase()
  if (['BTC', 'ETH', 'XRP', 'LTC', 'BCH', 'ADA', 'DOT', 'SOL', 'DOGE', 'MATIC', 'AVAX', 'LINK'].includes(s))
    return 'crypto'
  if (/^(EUR|GBP|USD|JPY|AUD|CAD|CHF|NZD)(EUR|GBP|USD|JPY|AUD|CAD|CHF|NZD)$/.test(s)) return 'forex'
  return 'stock'
}
