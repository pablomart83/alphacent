import { MetricGrid, SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import type { SystemHealthPayload, TradingGate } from '../useGuardData'

interface HealthTilesProps {
  health: SystemHealthPayload | null | undefined
  loading?: boolean
}

/**
 * HealthTiles — 4 summary KPIs: Uptime · Error rate 5m · Avg response · Blockers.
 * Uptime is a best-effort compute (first monitoring-service last_cycle, or
 * N/A when the service hasn't reported yet).
 */
export function HealthTiles({ health, loading }: HealthTilesProps) {
  if (loading && !health) {
    return (
      <MetricGrid cols={4} gap={2}>
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-[64px]" />
        ))}
      </MetricGrid>
    )
  }

  const etoro = (health?.etoro_api ?? {}) as Record<string, unknown>
  const errorRate = Number(etoro.error_rate_5m ?? 0)
  const avgResponse = Number(etoro.avg_response_ms ?? 0)
  const blockers = (health?.trading_gates ?? []).filter((g: TradingGate) => g.blocking).length

  return (
    <MetricGrid cols={4} gap={2}>
      <Tile
        label="Monitoring"
        value={
          health?.monitoring_service && (health.monitoring_service as { running?: boolean }).running
            ? 'Running'
            : 'Stopped'
        }
        color={
          (health?.monitoring_service as { running?: boolean } | undefined)?.running
            ? 'var(--pnl-up)'
            : 'var(--pnl-down)'
        }
      />
      <Tile
        label="Error rate · 5m"
        value={`${(errorRate * 100).toFixed(1)}%`}
        color={
          errorRate >= 0.05
            ? 'var(--pnl-down)'
            : errorRate >= 0.01
              ? 'var(--status-warning)'
              : 'var(--pnl-up)'
        }
      />
      <Tile
        label="Avg response"
        value={avgResponse > 0 ? `${avgResponse.toFixed(0)}ms` : '—'}
        color={
          avgResponse >= 1500
            ? 'var(--pnl-down)'
            : avgResponse >= 600
              ? 'var(--status-warning)'
              : 'var(--text-0)'
        }
      />
      <Tile
        label="Blockers"
        value={String(blockers)}
        color={
          blockers > 0 ? 'var(--pnl-down)' : 'var(--pnl-up)'
        }
      />
    </MetricGrid>
  )
}

function Tile({ label, value, color }: { label: string; value: string; color: string }) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div className="mono tabular-nums text-[14px] mt-0.5" style={{ color }}>
        {value}
      </div>
    </div>
  )
}

export { SectionLabel }
