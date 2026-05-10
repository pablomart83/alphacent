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
