import { cn } from '@/lib/utils'
import { convictionColor } from '@/lib/design-tokens'

export interface ConvictionComponents {
  wf_edge?: number // 0-40
  signal_quality?: number // 0-25
  regime_fit?: number // 0-20
  asset_tradability?: number // 0-15
  fundamental?: number // -15 to +15
  carry?: number // -5 to +5
  crypto_cycle?: number // -5 to +5
  sentiment?: number // -1 to +1
  factor?: number // -6 to +6
}

interface ConvictionBarProps {
  score: number // 0-100
  components?: ConvictionComponents
  size?: 'mini' | 'default' | 'large'
  showValue?: boolean
  /** Render a vertical line at this score (e.g. 74 for LIVE equities). */
  threshold?: number
  className?: string
}

const HEIGHTS = { mini: 4, default: 8, large: 14 } as const

const SEGMENT_STYLES: Array<{
  key: keyof ConvictionComponents
  label: string
  color: string
  max: number
}> = [
  { key: 'wf_edge', label: 'WF Edge', color: 'var(--pnl-up)', max: 40 },
  { key: 'signal_quality', label: 'Signal Quality', color: 'var(--accent-primary)', max: 25 },
  { key: 'regime_fit', label: 'Regime Fit', color: 'var(--regime-up)', max: 20 },
  { key: 'asset_tradability', label: 'Asset Tradability', color: 'var(--accent-ticker)', max: 15 },
  { key: 'fundamental', label: 'Fundamental', color: 'var(--accent-secondary)', max: 15 },
  { key: 'carry', label: 'Carry', color: 'var(--status-warning)', max: 5 },
  { key: 'crypto_cycle', label: 'Crypto Cycle', color: 'var(--regime-vol)', max: 5 },
  { key: 'sentiment', label: 'Sentiment', color: 'var(--text-2)', max: 1 },
  { key: 'factor', label: 'Factor', color: 'var(--pnl-up-flash)', max: 6 },
]

export function ConvictionBar({
  score,
  components,
  size = 'default',
  showValue = true,
  threshold,
  className,
}: ConvictionBarProps) {
  const clamped = Math.max(0, Math.min(100, Number.isFinite(score) ? score : 0))
  const height = HEIGHTS[size]

  // Mini: single solid bar coloured by conviction heat gradient.
  if (size === 'mini' || !components) {
    const color = convictionColor(clamped)
    return (
      <div
        className={cn('inline-flex items-center gap-1.5', className)}
        title={`Conviction: ${clamped.toFixed(0)}`}
      >
        <div
          className="relative rounded-[2px] overflow-hidden flex-1 min-w-[48px]"
          style={{ height, backgroundColor: 'var(--bg-2)' }}
        >
          <div
            className="absolute inset-y-0 left-0"
            style={{ width: `${clamped}%`, backgroundColor: color }}
          />
          {threshold != null && (
            <div
              className="absolute inset-y-0 w-[1px]"
              style={{ left: `${Math.max(0, Math.min(100, threshold))}%`, backgroundColor: 'var(--text-0)' }}
              title={`Threshold ${threshold}`}
            />
          )}
        </div>
        {showValue && (
          <span className="mono text-[10px] tabular-nums text-[var(--text-1)]">
            {clamped.toFixed(0)}
          </span>
        )}
      </div>
    )
  }

  // Default / large: stacked bar with positive and negative segments.
  const positives: Array<{ label: string; color: string; value: number }> = []
  const negatives: Array<{ label: string; color: string; value: number }> = []
  SEGMENT_STYLES.forEach((seg) => {
    const v = components[seg.key] ?? 0
    if (v > 0) positives.push({ label: seg.label, color: seg.color, value: v })
    if (v < 0) negatives.push({ label: seg.label, color: seg.color, value: v })
  })

  const positiveTotal = positives.reduce((acc, s) => acc + s.value, 0)
  // Render on a 0-100 canvas — scale segments to their share of the final score.
  const scale = positiveTotal > 0 ? clamped / positiveTotal : 0

  return (
    <div className={cn('flex flex-col gap-1', className)}>
      <div
        className="relative rounded-[3px] overflow-hidden"
        style={{ height, backgroundColor: 'var(--bg-2)' }}
      >
        <div className="absolute inset-y-0 left-0 right-0 flex">
          {positives.map((seg, i) => (
            <div
              key={`${seg.label}-${i}`}
              style={{
                width: `${seg.value * scale}%`,
                backgroundColor: seg.color,
              }}
              title={`${seg.label}: +${seg.value.toFixed(1)}`}
            />
          ))}
        </div>
        {threshold != null && (
          <div
            className="absolute inset-y-0 w-[1px]"
            style={{ left: `${Math.max(0, Math.min(100, threshold))}%`, backgroundColor: 'var(--text-0)' }}
            title={`Threshold ${threshold}`}
          />
        )}
      </div>
      {(showValue || size === 'large') && (
        <div className="flex items-center justify-between text-[10px]">
          <span className="mono tabular-nums text-[var(--text-1)] font-semibold">
            {clamped.toFixed(0)}
          </span>
          {size === 'large' && negatives.length > 0 && (
            <span className="text-[var(--pnl-down)] mono tabular-nums">
              {negatives
                .reduce((a, s) => a + s.value, 0)
                .toFixed(1)}{' '}
              penalty
            </span>
          )}
          {threshold != null && (
            <span className="text-[var(--text-3)] mono">≥ {threshold}</span>
          )}
        </div>
      )}
    </div>
  )
}
