import { SectionLabel } from '@/components/layout'
import { MetricGrid } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { formatNumber, formatTimestamp } from '@/lib/utils'
import type { DataSyncStatusPayload } from '../useGuardData'

interface DbStatsCardProps {
  sync: DataSyncStatusPayload | null | undefined
  loading?: boolean
}

/**
 * DbStatsCard — historical_price_cache health: total bars, per-interval
 * counts, unique symbols, bar age bookends.
 */
export function DbStatsCard({ sync, loading }: DbStatsCardProps) {
  const stats = sync?.db_stats

  if (loading && !stats) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Price-bar DB</SectionLabel>
        <Skeleton className="h-[90px] w-full" />
      </section>
    )
  }

  if (!stats) {
    return null
  }

  if (stats.error) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Price-bar DB</SectionLabel>
        <div className="text-[10px] text-[var(--pnl-down)]">{stats.error}</div>
      </section>
    )
  }

  const totalBars = Number(stats.total_bars ?? 0)
  const unique = Number(stats.unique_symbols ?? 0)
  const latest = stats.latest_bar as string | null | undefined
  const oldest = stats.oldest_bar as string | null | undefined
  const byInterval = (stats.by_interval ?? {}) as Record<string, number>

  return (
    <section className="space-y-1.5">
      <SectionLabel>Price-bar DB</SectionLabel>
      <MetricGrid cols={4} gap={2}>
        <Tile label="Total bars" value={formatNumber(totalBars)} />
        <Tile label="Unique symbols" value={formatNumber(unique)} />
        <Tile label="Latest bar" value={formatTimestamp(latest, 'short') || '—'} mono />
        <Tile label="Oldest bar" value={formatTimestamp(oldest, 'short') || '—'} mono />
      </MetricGrid>
      {Object.keys(byInterval).length > 0 && (
        <div className="flex flex-wrap gap-1 pt-1">
          {Object.entries(byInterval).map(([interval, count]) => (
            <span
              key={interval}
              className="inline-flex items-center gap-1 px-1.5 h-[16px] rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)]"
            >
              <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                {interval}
              </span>
              <span className="mono tabular-nums text-[10px] text-[var(--text-1)]">
                {formatNumber(count)}
              </span>
            </span>
          ))}
        </div>
      )}
    </section>
  )
}

function Tile({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div className={`${mono ? 'mono' : ''} tabular-nums text-[13px] text-[var(--text-0)] mt-0.5 truncate`} title={value}>
        {value}
      </div>
    </div>
  )
}
