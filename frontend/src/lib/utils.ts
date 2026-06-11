import { type ClassValue, clsx } from 'clsx'
import { twMerge } from 'tailwind-merge'

/** Compose Tailwind class names with conflict resolution. */
export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs))
}

/** Format a number as USD currency. */
export function formatCurrency(
  value: number | null | undefined,
  options: { compact?: boolean; signed?: boolean; precision?: number } = {},
): string {
  if (value == null || Number.isNaN(value)) return '—'
  const { compact = false, signed = false, precision = 2 } = options
  const abs = Math.abs(value)
  const sign = value < 0 ? '-' : signed && value > 0 ? '+' : ''

  if (compact && abs >= 1_000_000) return `${sign}$${(abs / 1_000_000).toFixed(2)}M`
  if (compact && abs >= 1_000) return `${sign}$${(abs / 1_000).toFixed(1)}K`
  return `${sign}$${abs.toLocaleString('en-US', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  })}`
}

/** Format a percentage. Value expected as percent (e.g., 1.5 = 1.5%). */
export function formatPercentage(
  value: number | null | undefined,
  options: { signed?: boolean; precision?: number } = {},
): string {
  if (value == null || Number.isNaN(value)) return '—'
  const { signed = true, precision = 2 } = options
  const sign = value > 0 && signed ? '+' : ''
  return `${sign}${value.toFixed(precision)}%`
}

/** Format a number with tabular-friendly defaults. */
export function formatNumber(
  value: number | null | undefined,
  precision = 2,
): string {
  if (value == null || Number.isNaN(value)) return '—'
  return value.toLocaleString('en-US', {
    minimumFractionDigits: precision,
    maximumFractionDigits: precision,
  })
}

/**
 * Coerce any reasonable timestamp input into a Date, or null when it can't be
 * interpreted. Accepts ISO strings, epoch numbers (seconds OR milliseconds —
 * auto-detected), and Date objects. This is the single guard that prevents
 * `x.getTime is not a function` when a non-string, non-Date value (e.g. an
 * epoch number from the API) reaches a date formatter.
 */
export function coerceToDate(
  value: string | number | Date | null | undefined,
): Date | null {
  if (value == null) return null
  if (value instanceof Date) return Number.isNaN(value.getTime()) ? null : value
  if (typeof value === 'string') {
    const d = parseUtcIso(value)
    return Number.isNaN(d.getTime()) ? null : d
  }
  if (typeof value === 'number' && Number.isFinite(value)) {
    // Heuristic: values below 1e12 are epoch SECONDS, at/above are milliseconds.
    // Covers both common backend conventions without a year-33658 mishap.
    const ms = value < 1e12 ? value * 1000 : value
    const d = new Date(ms)
    return Number.isNaN(d.getTime()) ? null : d
  }
  return null
}

/** Format an ISO timestamp for display. Defaults to local 'MMM d, HH:mm'. */
export function formatTimestamp(
  iso: string | number | Date | null | undefined,
  format: 'short' | 'long' | 'date' | 'time' = 'short',
): string {
  const parsed = coerceToDate(iso)
  if (!parsed) return '—'

  switch (format) {
    case 'long':
      return parsed.toLocaleString('en-GB', {
        year: 'numeric',
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    case 'date':
      return parsed.toLocaleDateString('en-GB', {
        month: 'short',
        day: 'numeric',
      })
    case 'time':
      return parsed.toLocaleTimeString('en-GB', {
        hour: '2-digit',
        minute: '2-digit',
      })
    case 'short':
    default:
      return parsed.toLocaleString('en-GB', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      })
  }
}

/**
 * Parse an ISO string, defensively appending `Z` if the backend emitted a
 * naive UTC timestamp (no timezone suffix). JS would otherwise interpret
 * those as local time and produce an N-hour drift.
 */
export function parseUtcIso(iso: string): Date {
  if (!iso) return new Date(NaN)
  let s = iso
  if (!/[zZ]|[+-]\d{2}:?\d{2}$/.test(s)) s = `${s}Z`
  return new Date(s)
}

/** Human-readable age from an ISO timestamp: "23s ago", "4m ago", "2.1h ago". */
export function formatAge(iso: string | number | Date | null | undefined): string {
  const d = coerceToDate(iso)
  if (!d) return '—'
  const age = (Date.now() - d.getTime()) / 1000
  if (age < 0) return 'just now'
  if (age < 60) return `${Math.round(age)}s ago`
  if (age < 3600) return `${Math.round(age / 60)}m ago`
  if (age < 86_400) return `${(age / 3600).toFixed(1)}h ago`
  return `${(age / 86_400).toFixed(1)}d ago`
}

/** Clamp a number between min and max. */
export function clamp(value: number, min: number, max: number): number {
  return Math.min(Math.max(value, min), max)
}
