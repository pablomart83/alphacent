import type { ReactNode } from 'react'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { cn } from '@/lib/utils'

type StatTone = 'default' | 'up' | 'down' | 'warn' | 'info' | 'muted'
type StatSize = 'sm' | 'md' | 'lg'

export interface StatTileProps {
  /** Uppercase caption above the value. */
  label: ReactNode
  /** Pre-formatted value. Ignored when `pnl` is supplied. */
  value?: ReactNode
  /** Render the value through PnLNumber (auto up/down colour + optional flash). */
  pnl?: {
    value: number
    format?: 'currency' | 'percentage' | 'decimal'
    precision?: number
    compact?: boolean
    flashOnChange?: boolean
    showSign?: boolean
  }
  /** Secondary line under the value, e.g. "of 5% · 20%". */
  sublabel?: ReactNode
  /** Semantic colour for the value (ignored when `pnl` or `valueColor` set). */
  tone?: StatTone
  /** Explicit value colour override (wins over `tone`). */
  valueColor?: string
  size?: StatSize
  /** Monospaced tabular value. Default true. */
  mono?: boolean
  /** Render value above the label (big-number KPI style). Default 'label-top'. */
  layout?: 'label-top' | 'value-top'
  /** Pulse just the value (draws the eye to a nonzero count without recolouring the tile). */
  pulseValue?: boolean
  /** 0-100(+) progress bar. Null/undefined hides it. */
  progress?: number | null
  /** 'limit' colours by threshold (>=90 red, >=60 amber, else green). */
  progressVariant?: 'limit' | 'plain'
  progressColor?: string
  /** Pulsing warning border — draws attention (e.g. a breached limit). */
  highlight?: boolean
  /** Dim the tile and show it's not fresh. */
  stale?: boolean
  /** Custom background (e.g. severity-tinted KPI). */
  bg?: string
  icon?: ReactNode
  /** Makes the whole tile a clickable/keyboard-focusable button. */
  onClick?: () => void
  title?: string
  className?: string
  valueClassName?: string
}

const TONE_COLOR: Record<StatTone, string> = {
  default: 'var(--text-0)',
  up: 'var(--pnl-up)',
  down: 'var(--pnl-down)',
  warn: 'var(--status-warning)',
  info: 'var(--accent-primary)',
  muted: 'var(--text-2)',
}

const SIZE_CLASS: Record<StatSize, string> = {
  sm: 'text-[13px] font-semibold',
  md: 'text-[14px] font-semibold',
  lg: 'text-[22px] font-bold leading-tight',
}

function limitColor(progress: number): string {
  if (progress >= 90) return 'var(--pnl-down)'
  if (progress >= 60) return 'var(--status-warning)'
  return 'var(--pnl-up)'
}

/**
 * Shared KPI tile — the single source of truth for the "uppercase label +
 * mono tabular value (+ optional sublabel / progress bar / attention pulse)"
 * pattern that was previously hand-rolled in MetricsStrip, RiskMetricTiles,
 * IntelSummaryTiles, DemoLiveSplitTile, LiveTradingHealthCard and AlphaGenTile.
 */
export function StatTile({
  label,
  value,
  pnl,
  sublabel,
  tone = 'default',
  valueColor,
  size = 'sm',
  mono = true,
  layout = 'label-top',
  pulseValue,
  progress,
  progressVariant = 'limit',
  progressColor,
  highlight,
  stale,
  bg,
  icon,
  onClick,
  title,
  className,
  valueClassName,
}: StatTileProps) {
  const color = valueColor ?? TONE_COLOR[tone]
  const barColor =
    progress == null
      ? undefined
      : progressColor ?? (progressVariant === 'limit' ? limitColor(progress) : 'var(--accent-primary)')

  const Wrapper: 'button' | 'div' = onClick ? 'button' : 'div'

  const labelEl = (
    <span className="flex items-center gap-1 text-[9px] uppercase tracking-wider text-[var(--text-3)] font-medium">
      {icon}
      <span className="truncate" title={typeof label === 'string' ? label : undefined}>
        {label}
      </span>
    </span>
  )

  const valueEl = pnl ? (
    <PnLNumber
      value={pnl.value}
      format={pnl.format ?? 'currency'}
      precision={pnl.precision ?? 2}
      compact={pnl.compact}
      flashOnChange={pnl.flashOnChange}
      showSign={pnl.showSign}
      size={size === 'lg' ? 'xl' : 'md'}
    />
  ) : (
    <span
      className={cn(
        SIZE_CLASS[size],
        mono && 'mono tabular-nums',
        pulseValue && 'animate-pulse',
        valueClassName,
      )}
      style={{ color }}
    >
      {value}
    </span>
  )

  return (
    <Wrapper
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      title={title}
      className={cn(
        'flex flex-col gap-0.5 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-left',
        onClick && 'cursor-pointer transition-colors hover:border-[var(--border-strong)] hover:bg-[var(--bg-hover)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--border-focus)]',
        highlight &&
          'border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_6%,var(--bg-1))] animate-pulse',
        stale && 'opacity-60',
        className,
      )}
      style={bg ? { background: bg } : undefined}
    >
      {layout === 'value-top' ? (
        <>
          {valueEl}
          {labelEl}
        </>
      ) : (
        <>
          {labelEl}
          {valueEl}
        </>
      )}

      {sublabel != null && (
        <span className="text-[9px] text-[var(--text-3)] mono tabular-nums truncate">
          {sublabel}
        </span>
      )}

      {progress != null && (
        <div className="mt-1 h-1 overflow-hidden rounded-[1px] bg-[var(--bg-0)]">
          <div
            className="h-full transition-[width]"
            style={{
              width: `${Math.max(0, Math.min(100, progress))}%`,
              backgroundColor: barColor,
            }}
          />
        </div>
      )}
    </Wrapper>
  )
}

type InlineTone = 'default' | 'up' | 'down' | 'strong' | 'muted'
type InlineSize = 'xs' | 'sm' | 'md'

export interface StatInlineProps {
  label: ReactNode
  value: ReactNode
  tone?: InlineTone
  /** Explicit value colour (wins over tone). */
  valueColor?: string
  size?: InlineSize
  mono?: boolean
  className?: string
}

const INLINE_TONE: Record<InlineTone, string> = {
  default: 'var(--text-1)',
  up: 'var(--pnl-up)',
  down: 'var(--pnl-down)',
  strong: 'var(--text-0)',
  muted: 'var(--text-3)',
}

const INLINE_VALUE_CLASS: Record<InlineSize, string> = {
  xs: 'text-[10px] font-medium',
  sm: 'text-[11px] font-medium',
  md: 'text-[15px] font-bold',
}

/**
 * Borderless label-over-value mini-stat used *inside* composite cards
 * (account splits, live-health, alpha tiles). Consolidates three identical
 * hand-rolled `Stat`/`ReturnCell` helpers into one shared primitive.
 */
export function StatInline({
  label,
  value,
  tone = 'default',
  valueColor,
  size = 'sm',
  mono = true,
  className,
}: StatInlineProps) {
  return (
    <div className={cn('flex flex-col gap-0.5', className)}>
      <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      <span
        className={cn(INLINE_VALUE_CLASS[size], mono && 'mono tabular-nums')}
        style={{ color: valueColor ?? INLINE_TONE[tone] }}
      >
        {value}
      </span>
    </div>
  )
}
