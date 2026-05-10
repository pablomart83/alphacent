import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'
import type { TradingMode } from '@/stores'

/**
 * Data hooks for the Settings surface.
 *
 * Settings queries use longer staleTime (5min) because the config file
 * doesn't change outside of UI-triggered writes. After a successful PUT,
 * we invalidate the matching query so the form snaps back to the canonical
 * server state — no optimistic drift.
 */

/* ============================================================
 * Credentials + connection status
 * ============================================================ */

export interface ConnectionStatus {
  connected: boolean
  mode?: TradingMode
  message: string
}

export function useConnectionStatus(mode: TradingMode, enabled = true) {
  return useQuery<ConnectionStatus>({
    queryKey: ['config-connection', mode],
    queryFn: () => api.get<ConnectionStatus>('/config/connection-status', { mode }),
    staleTime: 30_000,
    enabled,
  })
}

export interface SetCredentialsInput {
  mode: TradingMode
  public_key: string
  user_key: string
}

export function useSetCredentials() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: SetCredentialsInput) =>
      api.post('/config/credentials', body),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['config-connection', vars.mode] })
    },
  })
}

/* ============================================================
 * Risk + position management config
 * ============================================================ */

export interface RiskConfigShape {
  mode: TradingMode
  max_position_size_pct: number
  max_exposure_pct: number
  max_daily_loss_pct: number
  max_drawdown_pct: number
  position_risk_pct: number
  stop_loss_pct: number
  take_profit_pct: number
  trailing_stop_enabled?: boolean | null
  trailing_stop_activation_pct?: number | null
  trailing_stop_distance_pct?: number | null
  partial_exit_enabled?: boolean | null
  partial_exit_levels?: Array<Record<string, number>> | null
  correlation_adjustment_enabled?: boolean | null
  correlation_threshold?: number | null
  correlation_reduction_factor?: number | null
  regime_based_sizing_enabled?: boolean | null
  regime_multipliers?: Record<string, number> | null
  cancel_stale_orders?: boolean | null
  stale_order_hours?: number | null
}

export function useRiskConfig(mode: TradingMode) {
  return useQuery<RiskConfigShape>({
    queryKey: ['config-risk', mode],
    queryFn: () => api.get<RiskConfigShape>('/config/risk', { mode }),
    staleTime: 5 * 60_000,
  })
}

export function useUpdateRiskConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RiskConfigShape) => api.put('/config/risk', body),
    onSuccess: (_res, vars) => {
      qc.invalidateQueries({ queryKey: ['config-risk', vars.mode] })
    },
  })
}

/* ============================================================
 * Autonomous config — large, lives in a single yaml block
 * ============================================================ */

export type AutonomousConfigPayload = Record<string, unknown>

export function useAutonomousConfig() {
  return useQuery<AutonomousConfigPayload>({
    queryKey: ['config-autonomous'],
    queryFn: () => api.get<AutonomousConfigPayload>('/config/autonomous'),
    staleTime: 5 * 60_000,
  })
}

export function useUpdateAutonomousConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AutonomousConfigPayload) =>
      api.put('/config/autonomous', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config-autonomous'] })
    },
  })
}

/* ============================================================
 * Alpha Edge config
 * ============================================================ */

export type AlphaEdgeConfigShape = Record<string, unknown>

export function useAlphaEdgeConfig() {
  return useQuery<AlphaEdgeConfigShape>({
    queryKey: ['config-alpha-edge'],
    queryFn: () => api.get<AlphaEdgeConfigShape>('/config/alpha-edge'),
    staleTime: 5 * 60_000,
  })
}

export function useUpdateAlphaEdgeConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: AlphaEdgeConfigShape) =>
      api.put('/config/alpha-edge', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config-alpha-edge'] })
    },
  })
}

export interface ApiUsageShape {
  fmp?: Record<string, unknown>
  alpha_vantage?: Record<string, unknown>
  [k: string]: unknown
}

export function useApiUsage() {
  return useQuery<ApiUsageShape>({
    queryKey: ['config-alpha-edge-api-usage'],
    queryFn: () => api.get<ApiUsageShape>('/config/alpha-edge/api-usage'),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })
}

/* ============================================================
 * Live trading config
 * ============================================================ */

export interface LiveTradingConfigShape {
  enabled: boolean
  base_risk_pct: number
  min_order_size: number
  max_order_size: number
  symbol_cap: number
  mirror_ratio: number
  conviction_threshold: number
  conviction_threshold_crypto: number
  [k: string]: unknown
}

export function useLiveTradingConfig() {
  return useQuery<LiveTradingConfigShape>({
    queryKey: ['config-live-trading'],
    queryFn: () => api.get<LiveTradingConfigShape>('/config/live-trading'),
    staleTime: 30_000,
  })
}

export function useUpdateLiveTradingConfig() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: Partial<LiveTradingConfigShape>) =>
      api.put('/config/live-trading', body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['config-live-trading'] })
    },
  })
}

/* ============================================================
 * Users (admin only — tolerant on 403)
 * ============================================================ */

export interface UserRecord {
  username: string
  role: string
  permissions?: string[]
  is_active?: boolean
  created_at?: string
  last_login?: string | null
}

export function useUsers() {
  return useQuery<{ users: UserRecord[] }>({
    queryKey: ['users'],
    queryFn: () => api.get<{ users: UserRecord[] }>('/auth/users'),
    staleTime: 30_000,
  })
}

export function useRoles() {
  return useQuery<{ roles: Record<string, string[]> }>({
    queryKey: ['auth-roles'],
    queryFn: () => api.get<{ roles: Record<string, string[]> }>('/auth/roles'),
    staleTime: 5 * 60_000,
  })
}

export function useCreateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { username: string; password: string; role: string }) =>
      api.post('/auth/users', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      username,
      body,
    }: {
      username: string
      body: { role?: string; permissions?: string[]; is_active?: boolean }
    }) => api.put(`/auth/users/${encodeURIComponent(username)}`, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useDeleteUser() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (username: string) =>
      api.delete(`/auth/users/${encodeURIComponent(username)}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['users'] }),
  })
}

export function useResetUserPassword() {
  return useMutation({
    mutationFn: ({ username, new_password }: { username: string; new_password: string }) =>
      api.post(`/auth/users/${encodeURIComponent(username)}/reset-password`, {
        new_password,
      }),
  })
}

export function useChangeOwnPassword() {
  return useMutation({
    mutationFn: (body: { old_password: string; new_password: string }) =>
      api.post('/auth/change-password', body),
  })
}
