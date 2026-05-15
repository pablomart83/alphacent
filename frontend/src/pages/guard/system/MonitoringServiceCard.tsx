import { CheckCircle2, XCircle, Clock as ClockIcon } from 'lucide-react'
import { useMemo } from 'react'
import { Skeleton } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatAge } from '@/lib/utils'
import type {
  MonitoringStatusPayload,
  SystemHealthPayload,
} from '../useGuardData'

interface MonitoringServiceCardProps {
  health: SystemHealthPayload | null | undefined
  monitoring: MonitoringStatusPayload | null | undefined
  loading?: boolean
}

const KNOWN_TASKS = [
  { key: 'position_sync', label: 'Position sync', interval: '60s' },
  { key: 'trailing_stops', label: 'Trailing stops', interval: '60s' },
  { key: 'partial_exits', label: 'Partial exits', interval: '5s' },
  { key: 'quick_update', label: 'Quick price update', interval: '10m' },
  { key: 'full_sync', label: 'Full price sync', interval: '55m' },
  { key: 'fundamental_exits', label: 'Fundamental exits', interval: '1d' },
]

/**
 * MonitoringServiceCard — running flag + sub-tasks grid. Reads
 * /data/monitoring/status for the per-task last_run, falls back to
 * /control/system-health.monitoring_service.sub_tasks where present.
 *
 * The API returns a nested structure:
 *   { main_loop: { position_sync: {...}, trailing_stops: {...}, ... },
 *     background: { quick_price_update: {...}, full_price_sync: {...} },
 *     daily: { fundamental_exits: {...} } }
 *
 * We flatten it here so each KNOWN_TASKS key resolves correctly.
 */
export function MonitoringServiceCard({
  health,
  monitoring,
  loading,
}: MonitoringServiceCardProps) {
  const running = !!(health?.monitoring_service as { running?: boolean } | undefined)?.running

  // Flatten the nested monitoring payload into a single lookup map.
  // The backend nests tasks under main_loop / background / daily.
  // The frontend KNOWN_TASKS keys must match the leaf keys in those groups.
  const flat = useMemo(() => {
    if (!monitoring) return {} as Record<string, { last_run?: string | null; duration_s?: number | null; status?: string }>
    const result: Record<string, { last_run?: string | null; duration_s?: number | null; status?: string }> = {}
    // Direct flat keys (legacy / future)
    for (const [k, v] of Object.entries(monitoring)) {
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const nested = v as Record<string, unknown>
        // If the value has a last_run or status field it's a leaf task entry
        if ('last_run' in nested || 'status' in nested || 'age' in nested) {
          result[k] = nested as { last_run?: string | null; duration_s?: number | null; status?: string }
        } else {
          // It's a group (main_loop, background, daily) — flatten its children
          for (const [ck, cv] of Object.entries(nested)) {
            if (cv && typeof cv === 'object' && !Array.isArray(cv)) {
              result[ck] = cv as { last_run?: string | null; duration_s?: number | null; status?: string }
            }
          }
        }
      }
    }
    return result
  }, [monitoring])

  return (
    <section className="space-y-1.5">
      <div className="flex items-center gap-2">
        <SectionLabel className="mb-0">Monitoring service</SectionLabel>
        <span
          className={cn(
            'inline-flex items-center gap-1 px-1.5 h-[16px] rounded-[3px] text-[9px] font-semibold uppercase tracking-wider',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${running ? 'var(--pnl-up)' : 'var(--pnl-down)'} 15%, transparent)`,
            color: running ? 'var(--pnl-up)' : 'var(--pnl-down)',
            border: `1px solid color-mix(in oklab, ${running ? 'var(--pnl-up)' : 'var(--pnl-down)'} 40%, transparent)`,
          }}
        >
          {running ? (
            <CheckCircle2 className="h-3 w-3" />
          ) : (
            <XCircle className="h-3 w-3" />
          )}
          {running ? 'Running' : 'Stopped'}
        </span>
      </div>
      {loading && !monitoring ? (
        <Skeleton className="h-[180px] w-full" />
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
          {KNOWN_TASKS.map((t) => {
            const m = (flat[t.key] ?? {}) as {
              last_run?: string | null
              duration_s?: number | null
              status?: string
            }
            const status = (m.status ?? (m.last_run ? 'healthy' : 'unknown')) as string
            const color =
              status === 'healthy' || status === 'ok'
                ? 'var(--pnl-up)'
                : status === 'stale' || status === 'warning'
                  ? 'var(--status-warning)'
                  : status === 'error' || status === 'fail'
                    ? 'var(--pnl-down)'
                    : 'var(--text-3)'
            return (
              <div
                key={t.key}
                className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-[11px] font-medium text-[var(--text-0)] truncate" title={t.label}>
                    {t.label}
                  </span>
                  <span
                    className="text-[9px] uppercase tracking-wider mono"
                    style={{ color }}
                  >
                    {status}
                  </span>
                </div>
                <div className="flex items-center justify-between text-[10px] text-[var(--text-3)]">
                  <span className="inline-flex items-center gap-1">
                    <ClockIcon className="h-3 w-3" />
                    {formatAge(m.last_run) || '—'}
                  </span>
                  <span className="mono">every {t.interval}</span>
                </div>
                {typeof m.duration_s === 'number' && m.duration_s >= 0 && (
                  <div className="text-[9px] text-[var(--text-3)] mono">
                    last took {m.duration_s.toFixed(2)}s
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </section>
  )
}
