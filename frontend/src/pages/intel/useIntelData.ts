import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/services/api'

/* ═══════════════════════════════════════════════════════════════════
 *  Intel page data hooks
 * ═══════════════════════════════════════════════════════════════════ */

// ── Response shapes ──────────────────────────────────────────────────────────

export interface IntelContextLink {
  label: string
  url: string
}

export interface IntelFinding {
  id: string
  check_id: string
  key: string
  category: string           // A-H
  severity: 'P0' | 'P1' | 'P2' | 'opportunity' | string
  title: string
  detail: string
  evidence: string
  recommended_action: string
  context_links: IntelContextLink[]
  ask_kiro_prompt: string
  first_seen: string | null
  last_seen: string | null
  occurrence_count: number
  lookback_days: number
  status: 'open' | 'dismissed' | 'resolved' | string
  dismissed_reason: string | null
  resolved_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface IntelRun {
  id: string
  started_at: string | null
  completed_at: string | null
  lookback_days: number
  findings_created: number
  findings_updated: number
  findings_total: number
  duration_s: number | null
  error: string | null
  status: 'running' | 'complete' | 'error' | string
}

export interface IntelSummary {
  p0_open: number
  p1_open: number
  p2_open: number
  opportunities_open: number
  resolved_this_week: number
  last_run_at: string | null
  last_run_duration_s: number | null
  last_run_findings: number | null
}

export interface IntelRunResponse {
  run_id: string
  status: string
  message: string
}

export interface IntelFindingsFilters {
  status?: string
  category?: string
  severity?: string
}

// ── Queries ──────────────────────────────────────────────────────────────────

export function useIntelSummary() {
  return useQuery<IntelSummary>({
    queryKey: ['intel-summary'],
    queryFn: () => api.get<IntelSummary>('/intel/summary'),
    refetchInterval: 60_000,
    staleTime: 30_000,
    retry: false,
  })
}

export function useIntelFindings(filters: IntelFindingsFilters = {}) {
  return useQuery<IntelFinding[]>({
    queryKey: ['intel-findings', filters],
    queryFn: () =>
      api.get<IntelFinding[]>('/intel/findings', {
        status: filters.status || 'open',
        category: filters.category || undefined,
        severity: filters.severity || undefined,
      }),
    staleTime: 30_000,
  })
}

export function useIntelFinding(id: string | null) {
  return useQuery<IntelFinding>({
    queryKey: ['intel-finding', id],
    queryFn: () => api.get<IntelFinding>(`/intel/findings/${id}`),
    enabled: !!id,
    staleTime: 30_000,
  })
}

export function useIntelRuns(limit = 20) {
  return useQuery<IntelRun[]>({
    queryKey: ['intel-runs'],
    queryFn: () => api.get<IntelRun[]>(`/intel/runs?limit=${limit}`),
    staleTime: 30_000,
  })
}

// ── Mutations ────────────────────────────────────────────────────────────────

export function useRunAnalysis() {
  const qc = useQueryClient()
  return useMutation<IntelRunResponse, Error, number>({
    mutationFn: (lookback_days: number) =>
      api.post<IntelRunResponse>('/intel/run', undefined, { lookback_days }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intel-findings'] })
      qc.invalidateQueries({ queryKey: ['intel-summary'] })
      qc.invalidateQueries({ queryKey: ['intel-runs'] })
    },
  })
}

export function useDismissFinding() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, { id: string; reason: string }>({
    mutationFn: ({ id, reason }) =>
      api.post(`/intel/findings/${id}/dismiss`, { reason }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intel-findings'] })
      qc.invalidateQueries({ queryKey: ['intel-summary'] })
    },
  })
}

export function useResolveFinding() {
  const qc = useQueryClient()
  return useMutation<unknown, Error, string>({
    mutationFn: (id: string) => api.post(`/intel/findings/${id}/resolve`),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['intel-findings'] })
      qc.invalidateQueries({ queryKey: ['intel-summary'] })
    },
  })
}

// ── Helpers ──────────────────────────────────────────────────────────────────

export function severityColor(severity: string): string {
  switch (severity) {
    case 'P0':
      return 'var(--pnl-down)'
    case 'P1':
      return 'var(--status-warning)'
    case 'P2':
      return '#eab308' // yellow-500
    case 'opportunity':
      return 'var(--accent-primary)'
    default:
      return 'var(--text-3)'
  }
}

export function severityBg(severity: string): string {
  switch (severity) {
    case 'P0':
      return 'rgba(239,68,68,0.12)'
    case 'P1':
      return 'rgba(245,158,11,0.12)'
    case 'P2':
      return 'rgba(234,179,8,0.10)'
    case 'opportunity':
      return 'rgba(59,130,246,0.10)'
    default:
      return 'var(--bg-1)'
  }
}

export function categoryLabel(cat: string): string {
  const labels: Record<string, string> = {
    A: 'Strategy Health',
    B: 'Execution Quality',
    C: 'Risk & Positions',
    D: 'Data Pipeline',
    E: 'Cycle & Signals',
    F: 'System Health',
    G: 'Alpha Opportunities',
    H: 'Config Integrity',
  }
  return labels[cat] ?? cat
}

export function formatAge(iso: string | null | undefined): string {
  if (!iso) return '—'
  const ts = iso.endsWith('Z') ? iso : iso + 'Z'
  const diff = Date.now() - new Date(ts).getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.floor(hrs / 24)}d ago`
}
