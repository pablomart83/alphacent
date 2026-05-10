import { useEffect, useRef, useState } from 'react'
import { cn, formatCurrency, formatNumber, formatPercentage } from '@/lib/utils'

type NumberFormat = 'currency' | 'percentage' | 'decimal'

interface PnLNumberProps {
  value: number | null | undefined
  format?: NumberFormat
  precision?: number
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl'
  /** Prepend `+` to positive values. Defaults true for non-zero. */
  showSign?: boolean
  /** Render without colour — inherits surrounding text. Useful inside coloured pills. */
  muted?: boolean
  /** Animate background flash on value change. */
  flashOnChange?: boolean
  /** Disable all animations (overrides flashOnChange). */
  animate?: boolean
  /** Render — passed through for composition (e.g. as a span inline). */
  className?: string
  /** Treat |value| < epsilon as flat (pnlFlat colour, no sign). */
  flatEpsilon?: number
  /** Wraps value — useful for things like `$12.3K` compact formatting. */
  compact?: boolean
  prefix?: React.ReactNode
  suffix?: React.ReactNode
}

const SIZE_CLASS: Record<NonNullable<PnLNumberProps['size']>, string> = {
  sm: 'text-[11px] font-medium',
  md: 'text-[12px] font-semibold',
  lg: 'text-[15px] font-semibold',
  xl: 'text-[18px] font-semibold',
  '2xl': 'text-[22px] font-bold',
  '3xl': 'text-[28px] font-bold',
}

function formatValue(
  value: number,
  format: NumberFormat,
  precision: number | undefined,
  showSign: boolean,
  compact: boolean,
): string {
  if (format === 'currency') {
    return formatCurrency(value, {
      signed: showSign,
      precision: precision ?? 2,
      compact,
    })
  }
  if (format === 'percentage') {
    return formatPercentage(value, { signed: showSign, precision: precision ?? 2 })
  }
  // decimal — default
  const base = formatNumber(value, precision ?? 2)
  if (showSign && value > 0) return `+${base}`
  return base
}

export function PnLNumber({
  value,
  format = 'currency',
  precision,
  size = 'md',
  showSign = true,
  muted = false,
  flashOnChange = true,
  animate = true,
  className,
  flatEpsilon = 0.0001,
  compact = false,
  prefix,
  suffix,
}: PnLNumberProps) {
  const previous = useRef<number | null>(null)
  const [flashClass, setFlashClass] = useState<string | null>(null)

  useEffect(() => {
    if (!flashOnChange || !animate) return
    if (value == null || Number.isNaN(value)) return

    const prev = previous.current
    if (prev != null && prev !== value) {
      const delta = value - prev
      if (Math.abs(delta) > flatEpsilon) {
        setFlashClass(delta > 0 ? 'pnl-flash-up' : 'pnl-flash-down')
        const t = window.setTimeout(() => setFlashClass(null), 420)
        previous.current = value
        return () => window.clearTimeout(t)
      }
    }
    previous.current = value
  }, [value, flashOnChange, animate, flatEpsilon])

  if (value == null || Number.isNaN(value)) {
    return (
      <span className={cn('mono text-[var(--text-3)]', SIZE_CLASS[size], className)}>
        —
      </span>
    )
  }

  const isFlat = Math.abs(value) < flatEpsilon
  const colour = muted
    ? undefined
    : isFlat
      ? 'text-[var(--pnl-flat)]'
      : value > 0
        ? 'text-[var(--pnl-up)]'
        : 'text-[var(--pnl-down)]'

  const text = formatValue(isFlat ? 0 : value, format, precision, showSign, compact)

  return (
    <span
      className={cn(
        'mono inline-flex items-baseline rounded-[2px] px-[2px] transition-colors',
        SIZE_CLASS[size],
        colour,
        flashClass,
        className,
      )}
      data-pnl-sign={isFlat ? 'flat' : value > 0 ? 'up' : 'down'}
    >
      {prefix}
      {text}
      {suffix}
    </span>
  )
}
