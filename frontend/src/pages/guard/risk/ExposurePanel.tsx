import { SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import type {
  DirectionalExposurePayload,
  ExposureBreakdown,
} from '../useGuardData'

interface ExposurePanelProps {
  sector: ExposureBreakdown[] | undefined
  assetClass: ExposureBreakdown[] | undefined
  directional: DirectionalExposurePayload | undefined
  loading?: boolean
}

/**
 * ExposurePanel — the "what am I concentrated in" block under the Risk tab.
 * Three stacked groups: sector bars, asset-class tiles, directional exposure
 * bar. Works off /risk/advanced.
 */
export function ExposurePanel({
  sector,
  assetClass,
  directional,
  loading,
}: ExposurePanelProps) {
  return (
    <section className="space-y-4">
      <SectorExposureBars rows={sector} loading={loading} />
      <AssetClassExposureTiles rows={assetClass} loading={loading} />
      <DirectionalExposureBar directional={directional} loading={loading} />
    </section>
  )
}

function SectorExposureBars({
  rows,
  loading,
}: {
  rows?: ExposureBreakdown[]
  loading?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <SectionLabel>Sector exposure</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1">
        {loading && !rows ? (
          <Skeleton className="h-24 w-full" />
        ) : !rows?.length ? (
          <div className="text-[10px] text-[var(--text-3)] py-2">No sector exposure yet.</div>
        ) : (
          rows
            .slice()
            .sort((a, b) => b.percentage - a.percentage)
            .map((row) => {
              const limit = row.limit ?? null
              const pct = row.percentage
              const overLimit = limit != null && pct > limit
              const color = overLimit
                ? 'var(--pnl-down)'
                : limit != null && pct > limit * 0.8
                  ? 'var(--status-warning)'
                  : 'var(--accent-primary)'
              return (
                <div key={row.name} className="text-[10px]">
                  <div className="flex items-baseline justify-between">
                    <span className="text-[var(--text-1)] truncate max-w-[55%]" title={row.name}>
                      {row.name}
                    </span>
                    <span className="mono tabular-nums text-[var(--text-2)]">
                      {formatCurrency(row.value, { precision: 0 })} · {formatPercentage(pct, { precision: 1 })}
                      {limit != null && (
                        <span className="text-[var(--text-3)]">
                          {' / '}
                          {formatPercentage(limit, { precision: 0 })}
                        </span>
                      )}
                    </span>
                  </div>
                  <div className="relative h-1.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden">
                    <div
                      className="h-full"
                      style={{
                        width: `${Math.max(0, Math.min(100, pct))}%`,
                        backgroundColor: color,
                      }}
                    />
                    {limit != null && (
                      <div
                        className="absolute inset-y-0 w-[1px] bg-[var(--text-0)]"
                        style={{ left: `${Math.max(0, Math.min(100, limit))}%` }}
                        title={`Limit ${formatPercentage(limit, { precision: 0 })}`}
                      />
                    )}
                  </div>
                </div>
              )
            })
        )}
      </div>
    </div>
  )
}

function AssetClassExposureTiles({
  rows,
  loading,
}: {
  rows?: ExposureBreakdown[]
  loading?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <SectionLabel>Asset class exposure</SectionLabel>
      {loading && !rows ? (
        <Skeleton className="h-16 w-full" />
      ) : !rows?.length ? (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-[10px] text-[var(--text-3)]">
          No asset-class exposure data.
        </div>
      ) : (
        <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-6 gap-2">
          {rows.map((row) => (
            <div
              key={row.name}
              className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2"
            >
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                {row.name}
              </div>
              <div className="mono tabular-nums text-[14px] text-[var(--text-0)] mt-0.5">
                {formatPercentage(row.percentage, { precision: 1 })}
              </div>
              <div className="text-[9px] text-[var(--text-3)] mt-0.5 mono tabular-nums">
                {formatCurrency(row.value, { precision: 0 })}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function DirectionalExposureBar({
  directional,
  loading,
}: {
  directional?: DirectionalExposurePayload
  loading?: boolean
}) {
  return (
    <div className="space-y-1.5">
      <SectionLabel>Directional exposure</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        {loading && !directional ? (
          <Skeleton className="h-10 w-full" />
        ) : !directional ? (
          <div className="text-[10px] text-[var(--text-3)]">No directional exposure.</div>
        ) : (
          <DirectionalBar directional={directional} />
        )}
      </div>
    </div>
  )
}

function DirectionalBar({ directional }: { directional: DirectionalExposurePayload }) {
  const longPct = Math.max(0, Math.min(100, directional.long_pct))
  const shortPct = Math.max(0, Math.min(100, directional.short_pct))
  const limit = directional.limit_pct ?? 60
  const netColor =
    Math.abs(directional.net_pct) > limit
      ? 'var(--pnl-down)'
      : Math.abs(directional.net_pct) > limit * 0.8
        ? 'var(--status-warning)'
        : 'var(--accent-primary)'
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between text-[10px]">
        <span className="text-[var(--pnl-up)] mono tabular-nums">
          L {formatPercentage(longPct, { precision: 1 })} · {formatCurrency(directional.long_value, { precision: 0 })}
        </span>
        <span className="text-[var(--text-3)] mono tabular-nums">
          Net <span style={{ color: netColor }}>{formatPercentage(directional.net_pct, { precision: 1 })}</span>
          <span className="text-[var(--text-3)]"> / ±{limit.toFixed(0)}%</span>
        </span>
        <span className="text-[var(--pnl-down)] mono tabular-nums">
          S {formatPercentage(shortPct, { precision: 1 })} · {formatCurrency(directional.short_value, { precision: 0 })}
        </span>
      </div>
      <div
        className={cn(
          'relative h-2 rounded-[1px] bg-[var(--bg-0)] overflow-hidden flex',
        )}
      >
        <div
          style={{ width: `${longPct}%`, backgroundColor: 'var(--pnl-up)' }}
          className="h-full"
          title={`Long ${formatPercentage(longPct, { precision: 1 })}`}
        />
        <div
          style={{ width: `${shortPct}%`, backgroundColor: 'var(--pnl-down)' }}
          className="h-full"
          title={`Short ${formatPercentage(shortPct, { precision: 1 })}`}
        />
        <div
          className="absolute inset-y-0 w-[1px] bg-[var(--text-0)] opacity-80"
          style={{ left: `${Math.max(0, Math.min(100, (100 / 2) * (1 + limit / 100)))}%` }}
          title={`Limit +${limit}%`}
        />
        <div
          className="absolute inset-y-0 w-[1px] bg-[var(--text-0)] opacity-80"
          style={{ left: `${Math.max(0, Math.min(100, (100 / 2) * (1 - limit / 100)))}%` }}
          title={`Limit -${limit}%`}
        />
      </div>
    </div>
  )
}
