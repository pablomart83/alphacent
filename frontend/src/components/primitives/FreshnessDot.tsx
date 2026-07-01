import { cn, coerceToDate, formatAge } from '@/lib/utils'

export interface FreshnessDotProps {
  /** When the data was last updated. Accepts ISO string, epoch, or Date. */
  since?: string | number | Date | null
  /** Pre-computed age in seconds (wins over `since` if both given). */
  ageSeconds?: number | null
  /** Amber once age exceeds this (seconds). Default 300 (5 min). */
  warnAfterSec?: number
  /** Red once age exceeds this (seconds). Default 900 (15 min). */
  staleAfterSec?: number
  /** Show the human-readable age next to the dot. */
  showAge?: boolean
  /** Override label (e.g. "Positions"). */
  label?: string
  className?: string
}

type Freshness = 'fresh' | 'warn' | 'stale' | 'unknown'

const DOT_COLOR: Record<Freshness, string> = {
  fresh: 'var(--pnl-up)',
  warn: 'var(--status-warning)',
  stale: 'var(--pnl-down)',
  unknown: 'var(--text-3)',
}

export function freshnessOf(
  ageSeconds: number | null,
  warnAfterSec = 300,
  staleAfterSec = 900,
): Freshness {
  if (ageSeconds == null || !Number.isFinite(ageSeconds)) return 'unknown'
  if (ageSeconds >= staleAfterSec) return 'stale'
  if (ageSeconds >= warnAfterSec) return 'warn'
  return 'fresh'
}

/**
 * A small traffic-light dot for data freshness / reconciliation status.
 * Research consistently flags stale valuations as where fund dashboards break
 * first — this makes staleness a first-class, glanceable signal.
 */
export function FreshnessDot({
  since,
  ageSeconds,
  warnAfterSec = 300,
  staleAfterSec = 900,
  showAge = false,
  label,
  className,
}: FreshnessDotProps) {
  const age =
    ageSeconds != null
      ? ageSeconds
      : (() => {
          const d = coerceToDate(since)
          return d ? (Date.now() - d.getTime()) / 1000 : null
        })()

  const level = freshnessOf(age, warnAfterSec, staleAfterSec)
  const color = DOT_COLOR[level]

  return (
    <span
      className={cn('inline-flex items-center gap-1 text-[10px] text-[var(--text-2)]', className)}
      title={
        level === 'unknown'
          ? 'Freshness unknown'
          : `${label ? label + ' · ' : ''}updated ${formatAge(since ?? (age != null ? Date.now() - age * 1000 : null))}`
      }
    >
      <span
        className={cn('h-1.5 w-1.5 rounded-full', level === 'stale' && 'animate-pulse')}
        style={{ backgroundColor: color }}
      />
      {label && <span className="text-[var(--text-3)] uppercase tracking-wider">{label}</span>}
      {showAge && <span className="mono tabular-nums">{formatAge(since ?? null)}</span>}
    </span>
  )
}
