import { cn } from '@/lib/utils'
import { regimeColor } from '@/lib/design-tokens'

export type Regime =
  | 'trending_up_strong'
  | 'trending_up'
  | 'trending_up_weak'
  | 'ranging'
  | 'ranging_high_vol'
  | 'ranging_low_vol'
  | 'trending_down_weak'
  | 'trending_down'
  | 'trending_down_strong'
  | 'high_vol'
  | 'volatile'
  | 'unknown'
  | string

type DataQuality = 'high' | 'medium' | 'low' | null | undefined

interface RegimePillProps {
  regime: Regime | null | undefined
  confidence?: number | null
  dataQuality?: DataQuality
  size?: 'sm' | 'md' | 'lg'
  showConfidence?: boolean
  className?: string
  onClick?: () => void
}

const SIZE_CLASS = {
  sm: 'h-[16px] px-1.5 text-[10px]',
  md: 'h-[20px] px-2 text-[11px]',
  lg: 'h-[24px] px-2.5 text-[12px]',
} as const

function formatRegime(regime: string | null | undefined): string {
  if (!regime) return 'Unknown'
  return regime
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function qualityDot(quality: DataQuality): { color: string; title: string } | null {
  if (!quality) return null
  switch (quality) {
    case 'high':
      return { color: 'var(--pnl-up)', title: 'High data quality' }
    case 'medium':
      return { color: 'var(--status-warning)', title: 'Medium data quality' }
    case 'low':
      return { color: 'var(--pnl-down)', title: 'Low data quality' }
    default:
      return null
  }
}

export function RegimePill({
  regime,
  confidence,
  dataQuality,
  size = 'md',
  showConfidence = true,
  className,
  onClick,
}: RegimePillProps) {
  const colour = regimeColor(regime || 'unknown')
  const label = formatRegime(regime)
  const dot = qualityDot(dataQuality)

  const Component = onClick ? 'button' : 'span'

  return (
    <Component
      type={onClick ? 'button' : undefined}
      onClick={onClick}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-[3px] font-medium uppercase tracking-wide',
        'border transition-colors',
        SIZE_CLASS[size],
        onClick && 'hover:brightness-110 cursor-pointer focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]',
        className,
      )}
      style={{
        color: colour,
        backgroundColor: `color-mix(in oklab, ${colour} 15%, transparent)`,
        borderColor: `color-mix(in oklab, ${colour} 40%, transparent)`,
      }}
    >
      <span>{label}</span>
      {showConfidence && typeof confidence === 'number' && (
        <span className="opacity-70 mono">
          {(confidence * 100).toFixed(0)}%
        </span>
      )}
      {dot && (
        <span
          className="inline-block h-1.5 w-1.5 rounded-full"
          style={{ backgroundColor: dot.color }}
          title={dot.title}
          aria-label={dot.title}
        />
      )}
    </Component>
  )
}
