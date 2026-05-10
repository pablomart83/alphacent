import { AlertTriangle, CheckCircle2, ShieldAlert } from 'lucide-react'
import { Skeleton } from '@/components/primitives'
import { cn } from '@/lib/utils'
import { riskScoreColor, type RiskMetricsPayload } from './useGuardData'

interface RiskScoreHeroProps {
  metrics: RiskMetricsPayload | null | undefined
  loading?: boolean
  onReasonClick?: (reason: string) => void
}

/**
 * RiskScoreHero — the pill + reason list at the top of the left panel.
 * The server already classifies `risk_score` (safe | warning | danger) and
 * returns up to 3-4 `risk_reasons` for the current level.
 */
export function RiskScoreHero({ metrics, loading, onReasonClick }: RiskScoreHeroProps) {
  if (loading && !metrics) {
    return (
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3 space-y-2">
        <Skeleton className="h-6 w-32" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    )
  }

  const score = metrics?.risk_score ?? 'safe'
  const color = riskScoreColor(score)
  const Icon =
    score === 'danger' ? ShieldAlert : score === 'warning' ? AlertTriangle : CheckCircle2
  const label =
    score === 'danger'
      ? 'Danger'
      : score === 'warning'
        ? 'Warning'
        : 'Safe'

  const reasons = metrics?.risk_reasons ?? []

  return (
    <section className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span
          className={cn(
            'inline-flex items-center gap-1.5 px-2 py-1 rounded-[3px] text-[11px] font-semibold uppercase tracking-wider',
            score === 'danger' && 'animate-pulse',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${color} 15%, transparent)`,
            color,
            border: `1px solid color-mix(in oklab, ${color} 40%, transparent)`,
          }}
        >
          <Icon className="h-3.5 w-3.5" />
          {label}
        </span>
        <span className="text-[10px] text-[var(--text-3)]">
          {metrics?.active_positions_count ?? 0} positions active
        </span>
      </div>

      {reasons.length === 0 ? (
        <p className="text-[10px] text-[var(--text-3)]">
          No concerns. Risk remains within all configured limits.
        </p>
      ) : (
        <ul className="space-y-1 text-[10px]">
          {reasons.slice(0, 5).map((reason, i) => (
            <li key={i}>
              <button
                type="button"
                onClick={() => onReasonClick?.(reason)}
                className={cn(
                  'text-left w-full flex items-baseline gap-1.5 text-[var(--text-2)]',
                  onReasonClick && 'hover:text-[var(--text-0)] cursor-pointer',
                )}
                disabled={!onReasonClick}
              >
                <span className="text-[var(--text-3)] shrink-0">·</span>
                <span>{reason}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </section>
  )
}
