import { MetricGrid, SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import {
  pctOfLimit,
  type RiskLimitsPayload,
  type RiskMetricsPayload,
} from './useGuardData'

interface RiskMetricTilesProps {
  metrics: RiskMetricsPayload | null | undefined
  limits: RiskLimitsPayload | null | undefined
  loading?: boolean
  highlightKey?: string | null
}

type TileKey = 'var' | 'current_dd' | 'max_dd' | 'leverage' | 'beta' | 'margin'

interface TileDef {
  key: TileKey
  label: string
  /** Value formatter (takes metrics object so tiles can reference multiple fields). */
  formatValue: (m: RiskMetricsPayload) => string
  /** Limit formatter — optional since Beta has no limit. */
  formatLimit?: (l: RiskLimitsPayload) => string | null
  /** Raw value + limit for the progress bar. Return null to hide the bar. */
  progress?: (m: RiskMetricsPayload, l: RiskLimitsPayload) => number | null
  /** Reasons keyword — which alert substrings should pulse this tile. */
  reasonMatches?: RegExp
}

const TILES: TileDef[] = [
  {
    key: 'var',
    label: 'Portfolio VaR (95%)',
    formatValue: (m) => formatCurrency(m.portfolio_var, { precision: 0 }),
    reasonMatches: /var/i,
  },
  {
    key: 'current_dd',
    label: 'Current Drawdown',
    formatValue: (m) => formatPercentage(m.current_drawdown, { precision: 2 }),
    formatLimit: (l) => formatPercentage(l.max_drawdown, { precision: 1 }),
    progress: (m, l) => pctOfLimit(m.current_drawdown, l.max_drawdown),
    reasonMatches: /drawdown|dd/i,
  },
  {
    key: 'max_dd',
    label: 'Max Drawdown (peak)',
    formatValue: (m) => formatPercentage(m.max_drawdown, { precision: 2 }),
    formatLimit: (l) => formatPercentage(l.max_drawdown, { precision: 1 }),
    progress: (m, l) => pctOfLimit(m.max_drawdown, l.max_drawdown),
    reasonMatches: /drawdown|dd/i,
  },
  {
    key: 'leverage',
    label: 'Leverage',
    formatValue: (m) => `${m.leverage.toFixed(2)}×`,
    formatLimit: (l) => `${l.max_leverage.toFixed(1)}×`,
    progress: (m, l) => pctOfLimit(m.leverage, l.max_leverage),
    reasonMatches: /leverage/i,
  },
  {
    key: 'beta',
    label: 'Portfolio β',
    formatValue: (m) => m.portfolio_beta.toFixed(2),
  },
  {
    key: 'margin',
    label: 'Margin Utilisation',
    formatValue: (m) => formatPercentage(m.margin_utilization, { precision: 1 }),
    formatLimit: () => '100%',
    progress: (m) => (Number.isFinite(m.margin_utilization) ? m.margin_utilization : null),
    reasonMatches: /margin/i,
  },
]

export function RiskMetricTiles({
  metrics,
  limits,
  loading,
  highlightKey,
}: RiskMetricTilesProps) {
  return (
    <section className="space-y-1.5">
      <SectionLabel>Risk metrics</SectionLabel>
      {loading && (!metrics || !limits) ? (
        <MetricGrid cols={3} gap={2}>
          {TILES.map((t) => (
            <Skeleton key={t.key} className="h-[64px]" />
          ))}
        </MetricGrid>
      ) : (
        <MetricGrid cols={3} gap={2}>
          {TILES.map((t) => {
            if (!metrics) return null
            const value = t.formatValue(metrics)
            const limit = t.formatLimit && limits ? t.formatLimit(limits) : null
            const progress = t.progress && limits ? t.progress(metrics, limits) : null
            const highlighted = !!highlightKey && !!t.reasonMatches?.test(highlightKey)
            return (
              <Tile
                key={t.key}
                label={t.label}
                value={value}
                limit={limit}
                progress={progress}
                highlighted={highlighted}
              />
            )
          })}
        </MetricGrid>
      )}
    </section>
  )
}

interface TileProps {
  label: string
  value: string
  limit: string | null
  progress: number | null
  highlighted: boolean
}

function Tile({ label, value, limit, progress, highlighted }: TileProps) {
  const barColor =
    progress == null
      ? 'var(--text-3)'
      : progress >= 90
        ? 'var(--pnl-down)'
        : progress >= 60
          ? 'var(--status-warning)'
          : 'var(--pnl-up)'
  return (
    <div
      className={cn(
        'rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 transition-colors',
        highlighted &&
          'border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_6%,var(--bg-1))] animate-pulse',
      )}
    >
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] truncate" title={label}>
        {label}
      </div>
      <div className="mono tabular-nums text-[14px] text-[var(--text-0)] mt-0.5">
        {value}
      </div>
      {limit && (
        <div className="text-[9px] text-[var(--text-3)] mt-0.5 mono tabular-nums">
          of {limit}
          {progress != null && (
            <span className="ml-1">
              · <span style={{ color: barColor }}>{progress.toFixed(0)}%</span>
            </span>
          )}
        </div>
      )}
      {progress != null && (
        <div className="h-1 rounded-[1px] bg-[var(--bg-0)] overflow-hidden mt-1">
          <div
            style={{
              width: `${Math.max(0, Math.min(100, progress))}%`,
              backgroundColor: barColor,
            }}
            className="h-full transition-[width]"
          />
        </div>
      )}
    </div>
  )
}
