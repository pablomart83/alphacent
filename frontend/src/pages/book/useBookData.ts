import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import { useTradingMode, type TradingMode } from '@/stores'

/* ───── Response shapes (mirror the backend Pydantic models) ───── */

export interface PositionRow {
  id: string
  strategy_id: string
  strategy_name: string | null
  symbol: string
  side: string
  quantity: number
  entry_price: number
  current_price: number
  unrealized_pnl: number
  unrealized_pnl_percent: number
  realized_pnl: number
  stop_loss: number | null
  take_profit: number | null
  opened_at: string
  closed_at: string | null
  etoro_position_id: string
  closure_reason: string | null
  invested_amount: number | null
  pending_closure: boolean | null
  sector: string | null
  asset_class: string | null
}

export interface PositionsPayload {
  positions: PositionRow[]
  total_count: number
  pending_count: number | null
  market_open: boolean | null
}

export interface FundamentalAlertRow extends PositionRow {
  flag_reason?: string
  flag_timestamp?: string
  fundamental_detail?: Record<string, unknown>
}

export interface FundamentalAlertsPayload {
  success: boolean
  alerts: FundamentalAlertRow[]
  count: number
}

/* ───── Queries ───── */

/** Scope defaults to the active trading mode. Callers can pin a specific mode (e.g. LIVE tab). */
function useMode(pin?: TradingMode): TradingMode {
  const active = useTradingMode((s) => s.mode)
  return pin ?? active
}

export function useOpenPositions(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<PositionsPayload>({
    queryKey: ['positions', mode],
    queryFn: () => api.get<PositionsPayload>('/account/positions', { mode }),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function usePendingOpenPositions(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<PositionsPayload>({
    queryKey: ['positions', mode, 'pending-open'],
    queryFn: () => api.get<PositionsPayload>('/account/positions/pending-open', { mode }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function usePendingClosures(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<PositionsPayload>({
    queryKey: ['pending-closures', mode],
    queryFn: () =>
      api.get<PositionsPayload>('/account/positions/pending-closures', { mode }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useFundamentalAlerts(pinMode?: TradingMode) {
  const mode = useMode(pinMode)
  return useQuery<FundamentalAlertsPayload>({
    queryKey: ['fundamental-alerts', mode],
    queryFn: () =>
      api.get<FundamentalAlertsPayload>('/account/positions/fundamental-alerts', { mode }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useClosedPositions(pinMode?: TradingMode, limit = 500) {
  const mode = useMode(pinMode)
  return useQuery<PositionsPayload>({
    queryKey: ['closed-positions', mode, { limit }],
    queryFn: () =>
      api.get<PositionsPayload>('/account/positions/closed', { mode, limit }),
    // Closed positions are history — don't poll.
    staleTime: 5 * 60_000,
  })
}

/* ───── Mutations ───── */

interface ClosePositionsVars {
  positionIds: string[]
  mode: TradingMode
}

export function useClosePositions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ positionIds, mode }: ClosePositionsVars) => {
      return api.post<{
        message: string
        closed_count: number
        failed: string[]
      }>('/account/positions/close', { position_ids: positionIds }, { mode })
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
      qc.invalidateQueries({ queryKey: ['pending-closures', vars.mode] })
      qc.invalidateQueries({ queryKey: ['account-info'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useCloseAllPositions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (mode: TradingMode) => {
      return api.post<{ message: string; closed_count: number }>(
        '/account/positions/close-all',
        undefined,
        { mode },
      )
    },
    onSuccess: (_data, mode) => {
      qc.invalidateQueries({ queryKey: ['positions', mode] })
      qc.invalidateQueries({ queryKey: ['pending-closures', mode] })
      qc.invalidateQueries({ queryKey: ['account-info'] })
      qc.invalidateQueries({ queryKey: ['dashboard'] })
    },
  })
}

export function useApproveClosure() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ positionId, mode }: { positionId: string; mode: TradingMode }) => {
      return api.post<{ success: boolean; message: string }>(
        `/account/positions/${positionId}/approve-closure`,
        undefined,
        { mode },
      )
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['pending-closures', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useApproveClosuresBulk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      positionIds,
      mode,
    }: {
      positionIds: string[]
      mode: TradingMode
    }) =>
      api.post<{ success_count: number; fail_count: number; errors: string[] | null }>(
        '/account/positions/approve-closures-bulk',
        { position_ids: positionIds },
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['pending-closures', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useDismissClosure() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ positionId, mode }: { positionId: string; mode: TradingMode }) =>
      api.post<{ success: boolean; message: string }>(
        `/account/positions/${positionId}/dismiss-closure`,
        undefined,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['pending-closures', vars.mode] })
      qc.invalidateQueries({ queryKey: ['fundamental-alerts', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useDismissFundamentalAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ positionId, mode }: { positionId: string; mode: TradingMode }) =>
      api.post<{ success: boolean; message: string }>(
        `/account/positions/${positionId}/dismiss-alert`,
        undefined,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['fundamental-alerts', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useSyncPositions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (mode: TradingMode) =>
      api.post<{ synced: number; added: number; updated: number }>(
        '/account/positions/sync',
        undefined,
        { mode },
      ),
    onSuccess: (_d, mode) => {
      qc.invalidateQueries({ queryKey: ['positions', mode] })
      qc.invalidateQueries({ queryKey: ['pending-closures', mode] })
      qc.invalidateQueries({ queryKey: ['account-info'] })
    },
  })
}

export interface ModifyRiskVars {
  positionId: string
  mode: TradingMode
  /** Omit to leave unchanged. Explicit `null` clears the level. */
  stop_loss?: number | null
  take_profit?: number | null
}

export interface ModifyRiskResponse {
  success: boolean
  position_id: string
  previous: { stop_loss: number | null; take_profit: number | null }
  current: { stop_loss: number | null; take_profit: number | null }
  warnings: string[]
}

export function useModifyPositionRisk() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      positionId,
      mode,
      stop_loss,
      take_profit,
    }: ModifyRiskVars) => {
      const body: Record<string, number | null> = {}
      if (stop_loss !== undefined) body.stop_loss = stop_loss
      if (take_profit !== undefined) body.take_profit = take_profit
      return api.put<ModifyRiskResponse>(
        `/account/positions/${positionId}/risk-levels`,
        body,
        { mode },
      )
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useDeleteClosedPositions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ positionIds, mode }: { positionIds: string[]; mode: TradingMode }) =>
      api.post<{ success: boolean; deleted: number; message: string }>(
        '/account/positions/delete-closed',
        { position_ids: positionIds },
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['closed-positions', vars.mode] })
    },
  })
}


/* ═════════════════════════════════════════════════════════════════════
 *  Orders — Sprint 3
 * ═════════════════════════════════════════════════════════════════════ */

export type OrderSide = 'BUY' | 'SELL'
export type OrderType = 'MARKET' | 'LIMIT' | 'STOP_LOSS' | 'TAKE_PROFIT'
export type OrderStatus =
  | 'PENDING'
  | 'SUBMITTED'
  | 'FILLED'
  | 'PARTIALLY_FILLED'
  | 'CANCELLED'
  | 'REJECTED'
  | 'FAILED'

export interface OrderRow {
  id: string
  strategy_id: string
  strategy_name: string | null
  symbol: string
  side: OrderSide
  order_type: OrderType
  quantity: number
  price: number | null
  stop_price: number | null
  status: OrderStatus
  created_at: string | null
  updated_at: string | null
  filled_at: string | null
  filled_price: number | null
  filled_quantity: number | null
  etoro_order_id: string | null
  expected_price: number | null
  slippage: number | null
  fill_time_seconds: number | null
  order_action: 'entry' | 'close' | 'retirement' | null
}

export interface OrdersPayload {
  orders: OrderRow[]
  total_count: number
}

export interface ExecutionQualityPayload {
  avg_slippage: number
  fill_rate: number
  avg_fill_time_seconds: number
  rejection_rate: number
  total_orders: number
  filled_orders: number
  rejected_orders: number
  pending_orders: number
  slippage_by_strategy: Record<string, number>
  rejection_reasons: Record<string, number>
}

export interface PlaceOrderBody {
  strategy_id: string
  symbol: string
  side: OrderSide
  order_type: OrderType
  quantity: number
  price?: number | null
  stop_price?: number | null
}

export function useOrders(
  opts: { status?: OrderStatus; limit?: number; pinMode?: TradingMode } = {},
) {
  const { status: statusFilter, limit = 0, pinMode } = opts
  const active = useTradingMode((s) => s.mode)
  const mode = pinMode ?? active
  return useQuery<OrdersPayload>({
    queryKey: ['orders', mode, { status: statusFilter ?? null, limit }],
    queryFn: () =>
      api.get<OrdersPayload>('/orders', {
        mode,
        status_filter: statusFilter,
        limit: limit || undefined,
      }),
    refetchInterval: 15_000,
    staleTime: 10_000,
  })
}

export function useExecutionQuality(period: '1D' | '1W' | '1M' | '3M', pinMode?: TradingMode) {
  const active = useTradingMode((s) => s.mode)
  const mode = pinMode ?? active
  return useQuery<ExecutionQualityPayload>({
    queryKey: ['execution-quality', mode, period],
    queryFn: () =>
      api.get<ExecutionQualityPayload>('/orders/execution-quality', { mode, period }),
    staleTime: 60_000,
  })
}

export function useCancelOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      orderId,
      mode,
    }: {
      orderId: string
      mode: TradingMode
    }) =>
      api.delete<{ success: boolean; message: string; order_id: string }>(
        `/orders/${orderId}`,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['orders', vars.mode] })
    },
  })
}

export function useDeleteOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      orderId,
      mode,
    }: {
      orderId: string
      mode: TradingMode
    }) =>
      api.delete<{ success: boolean; message: string; order_id: string }>(
        `/orders/${orderId}/permanent`,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['orders', vars.mode] })
    },
  })
}

export function useBulkDeleteOrders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      orderIds,
      mode,
    }: {
      orderIds: string[]
      mode: TradingMode
    }) =>
      api.post<{
        success_count: number
        fail_count: number
        deleted_order_ids: string[]
        failed_order_ids: string[]
      }>('/orders/bulk-delete', { order_ids: orderIds }, { mode }),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['orders', vars.mode] })
    },
  })
}

export function useClosePositionFromOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({
      orderId,
      mode,
    }: {
      orderId: string
      mode: TradingMode
    }) =>
      api.post<{ success: boolean; message: string; order_id: string; position_closed: boolean }>(
        `/orders/${orderId}/close-position`,
        undefined,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['orders', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}

export function useSyncOrders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (mode: TradingMode) =>
      api.post<{ synced: number; added: number; updated: number }>(
        '/orders/sync',
        undefined,
        { mode },
      ),
    onSuccess: (_d, mode) => {
      qc.invalidateQueries({ queryKey: ['orders', mode] })
    },
  })
}

export function usePlaceOrder() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ body, mode }: { body: PlaceOrderBody; mode: TradingMode }) =>
      api.post<{ success: boolean; message: string; order_id: string }>(
        '/orders',
        body,
        { mode },
      ),
    onSuccess: (_d, vars) => {
      qc.invalidateQueries({ queryKey: ['orders', vars.mode] })
      qc.invalidateQueries({ queryKey: ['positions', vars.mode] })
    },
  })
}


/* ═════════════════════════════════════════════════════════════════════
 *  Live trading — Sprint 4
 * ═════════════════════════════════════════════════════════════════════ */

export interface LiveSummary {
  virtual_balance: number
  virtual_equity: number
  real_equity: number
  mirror_ratio: number
  unrealized_pnl_virtual: number
  unrealized_pnl_real: number
  today_pnl_virtual: number
  today_pnl_real: number
  open_positions: number
  deployed_capital_virtual: number
  deployed_capital_real: number
  deployed_pct: number
  active_live_authorizations: number
  live_enabled: boolean
}

export interface LiveConfig {
  enabled: boolean
  virtual_balance: number
  real_investment: number
  mirror_ratio: number
  /** Percentage (e.g. 0.6 = 0.6%). */
  base_risk_pct: number
  min_order_size: number
  max_order_size: number
  /** Percentage. */
  symbol_cap_pct: number
  /** Percentage. */
  portfolio_heat_cap: number
  conviction_threshold: number
  conviction_threshold_crypto: number
  real_per_virtual_order: number
  max_real_per_order: number
  live_client_configured: boolean
}

/** Divergence row shape returned by /live/divergence. */
export interface LiveDivergenceRow {
  id: number
  strategy_id: string
  template_name: string
  symbol: string
  activated_at: string | null
  position_size: number | null
  sl_pct: number | null
  tp_pct: number | null
  conviction_min: number | null
  paper_trades: number
  paper_sharpe: number | null
  paper_win_rate: number | null
  paper_pnl: number | null
  live_trades: number
  live_sharpe: number | null
  live_win_rate: number | null
  live_pnl: number | null
  divergence_pct: number | null
  divergence_flag: boolean
}

export interface LiveDivergencePayload {
  divergence: LiveDivergenceRow[]
  count: number
}

export function useLiveSummary() {
  return useQuery<LiveSummary>({
    queryKey: ['live-summary'],
    queryFn: () => api.get<LiveSummary>('/live/summary'),
    refetchInterval: 30_000,
    staleTime: 15_000,
  })
}

export function useLiveConfig() {
  return useQuery<LiveConfig>({
    queryKey: ['live-config'],
    queryFn: () => api.get<LiveConfig>('/config/live-trading'),
    staleTime: 60_000,
  })
}

export function useUpdateLiveConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (body: Partial<Omit<LiveConfig, 'real_per_virtual_order' | 'max_real_per_order' | 'live_client_configured'>>) =>
      api.put<{ success: boolean; message: string }>('/config/live-trading', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-config'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
    },
  })
}

export function useLiveDivergence() {
  return useQuery<LiveDivergencePayload>({
    queryKey: ['live-divergence'],
    queryFn: () => api.get<LiveDivergencePayload>('/live/divergence'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

export function useRetireLiveStrategy() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (liveId: number) =>
      api.post<{ success: boolean; message: string; retired_at: string }>(
        `/live/strategies/${liveId}/retire`,
        undefined,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['live-divergence'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
    },
  })
}

export function useCloseLivePosition() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (positionId: string) =>
      api.post<{ success: boolean; message: string }>(
        `/live/positions/${positionId}/close`,
        undefined,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['positions', 'LIVE'] })
      qc.invalidateQueries({ queryKey: ['live-summary'] })
    },
  })
}
