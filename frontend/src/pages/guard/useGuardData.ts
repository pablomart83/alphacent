import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode, type TradingMode } from '@/stores'

/* ═════════════════════════════════════════════════════════════════════
 *  Guard data hooks — Sprint 8 (Risk + Gates).
 *  Wraps /risk/*, /control/system-health, and /control/* action endpoints.
 *  Sprint 9 adds: /audit/*, /data/*, /alerts/*, /control/circuit-breaker/*.
 * ═════════════════════════════════════════════════════════════════════ */

function useMode(pin?: TradingMode): TradingMode {
  const active = useTradingMode((s) => s.mode)
  return pin ?? active
}

/* ──── Response shapes ──── */

export type RiskScore = 'safe' | 'warning' | 'danger' | string

export interface RiskMetricsPayload {
  portfolio_var: number
  current_drawdown: number
  max_drawdown: number
  leverage: number
  margin_utilization: number
  portfolio_beta: number
  max_position_size: number
  total_exposure: number
  risk_score: RiskScore
  risk_reasons: string[]
  active_positions_count: number
  risk_breakdown: Record<string, number>
}

export interface RiskLimitsPayload {
  max_position_size: number
  max_portfolio_exposure: number
  max_daily_loss: number
  max_drawdown: number
  max_leverage: number
  risk_per_trade: number
}

export interface UpdateRiskLimitsBody {
  max_position_size?: number
  max_portfolio_exposure?: number
  max_daily_loss?: number
  max_drawdown?: number
  max_leverage?: number
  risk_per_trade?: number
}

export interface PositionRiskRow {
  position_id: string
  symbol: string
  strategy_id: string
  risk_amount: number
  risk_percent: number
  stop_loss: number | null
  take_profit: number | null
  risk_level: 'high' | 'medium' | 'low' | string
}

export interface RiskHistoryPoint {
  timestamp: string
  var: number
  drawdown: number
  leverage: number
  beta: number
}

export interface RiskHistoryPayload {
  history: RiskHistoryPoint[]
  period: string
}

export interface RiskAlertRow {
  id: string
  severity: 'info' | 'warning' | 'danger' | string
  metric: string
  current_value: number
  threshold: number
  message: string
  timestamp: string
}

export interface CorrelatedPair {
  symbol_a: string
  symbol_b: string
  correlation: number
  risk_level: string
}

export interface VaRResult {
  var_95: number
  var_99: number
  var_95_pct: number
  var_99_pct: number
  method: string
  trading_days_used: number
}

export interface StressScenario {
  name: string
  description: string
  estimated_loss: number
  estimated_loss_pct: number
  affected_positions: number
}

export interface MarginUtilization {
  used: number
  available: number
  total: number
  utilization_pct: number
  zone: 'green' | 'amber' | 'red' | string
}

export interface ExposureBreakdown {
  name: string
  value: number
  percentage: number
  limit?: number | null
}

export interface DirectionalExposurePayload {
  long_value: number
  long_pct: number
  short_value: number
  short_pct: number
  net_value: number
  net_pct: number
  limit_pct: number
}

export interface AdvancedRiskPayload {
  correlated_pairs: CorrelatedPair[]
  var: VaRResult
  stress_tests: StressScenario[]
  margin: MarginUtilization
  sector_exposure: ExposureBreakdown[]
  asset_class_exposure: ExposureBreakdown[]
  directional_exposure: DirectionalExposurePayload
}

export interface TradingGate {
  name: string
  armed: boolean
  blocking: boolean
  detail?: string | null
}

export interface SystemHealthPayload {
  circuit_breakers: Array<Record<string, unknown>>
  monitoring_service: Record<string, unknown>
  trading_scheduler: Record<string, unknown>
  etoro_api: Record<string, unknown>
  cache_stats: Record<string, unknown>
  events_24h: Array<Record<string, unknown>>
  background_threads: Record<string, Record<string, unknown>>
  trading_gates: TradingGate[]
  observability: Record<string, unknown>
}

export interface SystemStatus {
  state: 'ACTIVE' | 'PAUSED' | 'STOPPED' | 'EMERGENCY_HALT' | string
  timestamp: string
  reason?: string | null
}

export interface KillSwitchResponse {
  success: boolean
  message: string
  positions_closed?: number
  orders_cancelled?: number
}

/* ──── Queries ──── */

export function useRiskMetrics(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<RiskMetricsPayload>({
    queryKey: ['risk-metrics', mode],
    queryFn: () => api.get<RiskMetricsPayload>('/risk/metrics', { mode }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function useRiskLimits(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<RiskLimitsPayload>({
    queryKey: ['risk-limits', mode],
    queryFn: () => api.get<RiskLimitsPayload>('/risk/limits', { mode }),
    staleTime: 60_000,
  })
}

export function useRiskPositions(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<PositionRiskRow[]>({
    queryKey: ['risk-positions', mode],
    queryFn: () => api.get<PositionRiskRow[]>('/risk/positions', { mode }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useRiskHistory(period: string = '30d', pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<RiskHistoryPayload>({
    queryKey: ['risk-history', mode, period],
    queryFn: () => api.get<RiskHistoryPayload>('/risk/history', { mode, period }),
    staleTime: 120_000,
  })
}

export function useRiskAlerts(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<RiskAlertRow[]>({
    queryKey: ['risk-alerts', mode],
    queryFn: () => api.get<RiskAlertRow[]>('/risk/alerts', { mode }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useAdvancedRisk(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<AdvancedRiskPayload>({
    queryKey: ['risk-advanced', mode],
    queryFn: () => api.get<AdvancedRiskPayload>('/risk/advanced', { mode }),
    staleTime: 120_000,
  })
}

export function useSystemHealth() {
  return useQuery<SystemHealthPayload>({
    queryKey: ['system-health'],
    queryFn: () => api.get<SystemHealthPayload>('/control/system-health'),
    refetchInterval: 15_000,
    staleTime: 5_000,
  })
}

export function useSystemStatus() {
  return useQuery<SystemStatus>({
    queryKey: ['system-status'],
    queryFn: () => api.get<SystemStatus>('/control/system/status'),
    refetchInterval: 15_000,
    staleTime: 5_000,
  })
}

/* ──── Mutations ──── */

export function useUpdateRiskLimits() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      mode,
      body,
    }: {
      mode: TradingMode
      body: UpdateRiskLimitsBody
    }) => api.put('/risk/limits', body, { mode }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risk-limits'] })
      qc.invalidateQueries({ queryKey: ['risk-metrics'] })
      qc.invalidateQueries({ queryKey: ['risk-alerts'] })
    },
  })
}

export function useKillSwitch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<KillSwitchResponse>('/control/kill-switch', { confirmation: true }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['risk-metrics'] })
      qc.invalidateQueries({ queryKey: ['risk-positions'] })
      qc.invalidateQueries({ queryKey: ['risk-alerts'] })
      qc.invalidateQueries({ queryKey: ['positions'] })
      qc.invalidateQueries({ queryKey: ['orders'] })
      qc.invalidateQueries({ queryKey: ['system-status'] })
      qc.invalidateQueries({ queryKey: ['system-health'] })
    },
  })
}

export function useResetSystem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string; state: string }>(
        '/control/system/reset',
        { confirmation: true },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-status'] })
      qc.invalidateQueries({ queryKey: ['system-health'] })
    },
  })
}

/* ──── Helpers ──── */

/** Colour token for a `risk_score` value. */
export function riskScoreColor(score?: string | null): string {
  switch (score) {
    case 'safe':
      return 'var(--pnl-up)'
    case 'warning':
      return 'var(--status-warning)'
    case 'danger':
      return 'var(--pnl-down)'
    default:
      return 'var(--text-3)'
  }
}

/** Label — 'value of N limit' copy for tiles. */
export function pctOfLimit(value: number | null | undefined, limit: number | null | undefined): number | null {
  if (value == null || limit == null || !Number.isFinite(value) || !Number.isFinite(limit) || limit <= 0) return null
  return (value / limit) * 100
}
