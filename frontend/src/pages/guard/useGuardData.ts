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

/* ═════════════════════════════════════════════════════════════════════
 *  Sprint 9 — System / Circuit Breakers / Alerts / Audit
 * ═════════════════════════════════════════════════════════════════════ */

/* ──── System / data-management ──── */

export interface DataSyncQuickUpdate {
  last_run?: string | null
  duration_s?: number | null
  symbols_updated?: number | null
  errors?: number
}

export interface DataSyncDbStats {
  total_bars?: number
  by_interval?: Record<string, number>
  unique_symbols?: number
  latest_bar?: string | null
  oldest_bar?: string | null
  recent_1h_symbols?: Array<{ symbol: string; latest: string }>
  error?: string
  [key: string]: unknown
}

export interface DataSyncStatusPayload {
  last_sync_at?: string | null
  last_sync_success: boolean
  last_sync_duration_s?: number | null
  last_sync_stats?: Record<string, unknown> | null
  sync_running: boolean
  sync_interval_s: number
  db_stats?: DataSyncDbStats | null
  sync_logs?: string[] | null
  sync_elapsed_s?: number | null
  quick_update?: DataSyncQuickUpdate | null
}

export interface FmpCacheStatusPayload {
  total_symbols?: number
  fresh_count?: number
  any_count?: number
  coverage_pct?: number
  last_warm_at?: string | null
  running?: boolean
  [key: string]: unknown
}

export interface NewsSentimentStatusPayload {
  last_run?: string | null
  total_symbols?: number
  covered_symbols?: number
  coverage_pct?: number
  running?: boolean
  [key: string]: unknown
}

export interface MonitoringStatusPayload {
  [task: string]: {
    last_run?: string | null
    duration_s?: number | null
    status?: string
    interval_seconds?: number
    [key: string]: unknown
  }
}

export interface DataQualityEntry {
  symbol: string
  score?: number | null
  asset_class?: string | null
  issues?: string[]
  metrics?: Record<string, unknown>
  [key: string]: unknown
}

export interface DataQualityPayload {
  entries: DataQualityEntry[]
}

export function useDataSyncStatus(enabled = true) {
  return useQuery<DataSyncStatusPayload>({
    queryKey: ['data-sync-status'],
    queryFn: () => api.get<DataSyncStatusPayload>('/data/sync/status'),
    // Fast polling while a sync is running — caller reads `sync_running` and
    // flips the interval via `refetchInterval` callback.
    refetchInterval: (query) => {
      const data = query.state.data as DataSyncStatusPayload | undefined
      return data?.sync_running || data?.quick_update ? 5_000 : 30_000
    },
    staleTime: 3_000,
    enabled,
  })
}

export function useFmpCacheStatus() {
  return useQuery<FmpCacheStatusPayload>({
    queryKey: ['fmp-cache-status'],
    queryFn: () => api.get<FmpCacheStatusPayload>('/data/fmp-cache/status'),
    refetchInterval: 30_000,
    staleTime: 10_000,
  })
}

export function useNewsSentimentStatus() {
  return useQuery<NewsSentimentStatusPayload>({
    queryKey: ['news-sentiment-status'],
    queryFn: () => api.get<NewsSentimentStatusPayload>('/data/news-sentiment/status'),
    staleTime: 60_000,
  })
}

export function useMonitoringStatus() {
  return useQuery<MonitoringStatusPayload>({
    queryKey: ['monitoring-status'],
    queryFn: () => api.get<MonitoringStatusPayload>('/data/monitoring/status'),
    refetchInterval: 15_000,
    staleTime: 5_000,
  })
}

export function useDataQuality() {
  return useQuery<DataQualityPayload>({
    queryKey: ['data-quality'],
    queryFn: () => api.get<DataQualityPayload>('/data/quality'),
    staleTime: 120_000,
  })
}

/* Sync / warm / quick-update triggers */

function invalidateSystemHealth(qc: ReturnType<typeof useQueryClient>) {
  qc.invalidateQueries({ queryKey: ['data-sync-status'] })
  qc.invalidateQueries({ queryKey: ['fmp-cache-status'] })
  qc.invalidateQueries({ queryKey: ['monitoring-status'] })
  qc.invalidateQueries({ queryKey: ['news-sentiment-status'] })
  qc.invalidateQueries({ queryKey: ['system-health'] })
}

export function useTriggerFullSync() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string }>('/data/sync/trigger'),
    onSuccess: () => invalidateSystemHealth(qc),
  })
}

export function useTriggerQuickUpdate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string }>('/data/quick-update/trigger'),
    onSuccess: () => invalidateSystemHealth(qc),
  })
}

export function useTriggerFmpWarm() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string }>('/data/fmp-cache/trigger'),
    onSuccess: () => invalidateSystemHealth(qc),
  })
}

export function useTriggerNewsSentiment() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string }>('/data/news-sentiment/trigger'),
    onSuccess: () => invalidateSystemHealth(qc),
  })
}

/* ──── Circuit breakers ──── */

export interface CircuitBreakerEntry {
  category: string
  state: string
  failure_count: number
  cooldown_remaining_seconds: number
}

export function useResetCircuitBreaker() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean; message: string }>(
        '/control/circuit-breaker/reset',
        { confirmation: true },
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['system-health'] })
      qc.invalidateQueries({ queryKey: ['risk-metrics'] })
      qc.invalidateQueries({ queryKey: ['risk-alerts'] })
    },
  })
}

/* ──── Alerts ──── */

export type AlertSeverity = 'info' | 'warning' | 'critical' | string

export interface AlertHistoryRow {
  id: number
  alert_type: string
  severity: AlertSeverity
  title: string
  message: string
  metadata?: Record<string, unknown> | null
  read: boolean
  acknowledged: boolean
  link_page?: string | null
  created_at: string
}

export interface AlertHistoryPayload {
  success: boolean
  data: {
    alerts: AlertHistoryRow[]
    unread_count: number
    total: number
  }
}

export interface AlertConfigPayload {
  success: boolean
  data: {
    pnl_loss_enabled: boolean
    pnl_loss_threshold: number
    pnl_gain_enabled: boolean
    pnl_gain_threshold: number
    drawdown_enabled: boolean
    drawdown_threshold: number
    position_loss_enabled: boolean
    position_loss_threshold: number
    margin_enabled: boolean
    margin_threshold: number
    cycle_complete_enabled: boolean
    strategy_retired_enabled: boolean
    browser_push_enabled: boolean
    [key: string]: unknown
  }
}

export interface AlertHistoryFilters {
  limit?: number
  unread_only?: boolean
  severity?: AlertSeverity | null
}

export function useAlertHistory(filters: AlertHistoryFilters = {}) {
  return useQuery<AlertHistoryPayload>({
    queryKey: ['alerts-history', filters],
    queryFn: () =>
      api.get<AlertHistoryPayload>('/alerts/history', {
        limit: filters.limit ?? 100,
        unread_only: filters.unread_only || undefined,
        severity: filters.severity || undefined,
      }),
    refetchInterval: 60_000,
    staleTime: 15_000,
  })
}

export function useAlertConfig() {
  return useQuery<AlertConfigPayload>({
    queryKey: ['alerts-config'],
    queryFn: () => api.get<AlertConfigPayload>('/alerts/config'),
    staleTime: 300_000,
  })
}

export function useMarkAlertRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) =>
      api.post<{ success: boolean }>(`/alerts/history/${id}/read`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-history'] }),
  })
}

export function useMarkAllAlertsRead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () =>
      api.post<{ success: boolean }>('/alerts/history/read-all'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-history'] }),
  })
}

export function useAcknowledgeAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (id: number) =>
      api.post<{ success: boolean }>(`/alerts/history/${id}/acknowledge`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-history'] }),
  })
}

export function useClearAlertHistory() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async () => api.delete<{ success: boolean }>('/alerts/history'),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-history'] }),
  })
}

export function useUpdateAlertConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: AlertConfigPayload['data']) =>
      api.put<AlertConfigPayload>('/alerts/config', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts-config'] }),
  })
}

/* ──── Audit ──── */

export type AuditEventType = 'signal' | 'order' | 'position' | 'strategy' | 'rejection' | string

export interface AuditLogEntry {
  id: string
  timestamp: string
  event_type: AuditEventType
  symbol?: string | null
  strategy_name?: string | null
  severity: 'info' | 'warning' | 'danger' | string
  description: string
  metadata?: Record<string, unknown> | null
}

export interface AuditLogPayload {
  entries: AuditLogEntry[]
  total: number
  offset: number
  limit: number
}

export interface AuditLogFilters {
  event_types?: AuditEventType[]
  symbol?: string | null
  severity?: string | null
  start_date?: string | null
  end_date?: string | null
  search?: string | null
  offset?: number
  limit?: number
}

export function useAuditLog(filters: AuditLogFilters = {}) {
  return useQuery<AuditLogPayload>({
    queryKey: ['audit-log', filters],
    queryFn: () =>
      api.get<AuditLogPayload>('/audit/log', {
        event_types: filters.event_types?.length
          ? filters.event_types.join(',')
          : undefined,
        symbol: filters.symbol || undefined,
        severity: filters.severity || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        search: filters.search || undefined,
        offset: filters.offset ?? 0,
        limit: filters.limit ?? 200,
      }),
    staleTime: 30_000,
  })
}

export interface TradeLifecycleStep {
  step: string
  timestamp?: string | null
  details: Record<string, unknown>
}

export interface TradeLifecyclePayload {
  trade_id: string
  symbol?: string | null
  strategy_name?: string | null
  steps: TradeLifecycleStep[]
}

export function useTradeLifecycle(tradeId: string | null) {
  return useQuery<TradeLifecyclePayload>({
    queryKey: ['trade-lifecycle', tradeId],
    queryFn: () =>
      api.get<TradeLifecyclePayload>(`/audit/trade-lifecycle/${tradeId}`),
    enabled: !!tradeId,
    staleTime: 60_000,
  })
}

/** Build a URL suitable for `<a href>` to /audit/export so the browser can
 *  stream the response. CSV export leaves the page, so we don't need a
 *  mutation — just a URL builder with the current filters. */
export function buildAuditExportUrl(filters: AuditLogFilters): string {
  const base = import.meta.env.VITE_API_BASE_URL || ''
  const params = new URLSearchParams()
  if (filters.event_types?.length) params.set('event_types', filters.event_types.join(','))
  if (filters.symbol) params.set('symbol', filters.symbol)
  if (filters.severity) params.set('severity', filters.severity)
  if (filters.start_date) params.set('start_date', filters.start_date)
  if (filters.end_date) params.set('end_date', filters.end_date)
  if (filters.search) params.set('search', filters.search)
  const qs = params.toString()
  return `${base}/audit/export${qs ? `?${qs}` : ''}`
}

/* ═════════════════════════════════════════════════════════════════════
 *  Service Log — Guard → Sync Log tab
 * ═════════════════════════════════════════════════════════════════════ */

export type ServiceLogLevel = 'info' | 'success' | 'warning' | 'error'

export interface ServiceLogEntry {
  seq: number
  ts: string
  ts_iso: string
  service: string
  event: string
  level: ServiceLogLevel
  detail?: string | null
}

export interface ServiceLogPayload {
  entries: ServiceLogEntry[]
  total: number
}

export function useServiceLog(enabled = true) {
  return useQuery<ServiceLogPayload>({
    queryKey: ['service-log'],
    queryFn: () => api.get<ServiceLogPayload>('/data/service-log?limit=300'),
    enabled,
    refetchInterval: 5_000,
    staleTime: 4_000,
  })
}
