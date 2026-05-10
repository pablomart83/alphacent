import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'

export interface HealthScore {
  score: number // 0-100
  drawdown_score: number // 0-25
  concentration_score: number // 0-25
  margin_score: number // 0-25
  diversity_score: number // 0-25
}

interface HealthScoreCardProps {
  health: HealthScore | null | undefined
  className?: string
}

const SEGMENT_META: Array<{
  key: keyof HealthScore
  label: string
  color: string
  max: number
}> = [
  { key: 'drawdown_score', label: 'Drawdown', color: 'var(--pnl-up)', max: 25 },
  { key: 'concentration_score', label: 'Concentration', color: 'var(--accent-primary)', max: 25 },
  { key: 'margin_score', label: 'Margin', color: 'var(--accent-ticker)', max: 25 },
  { key: 'diversity_score', label: 'Diversity', color: 'var(--regime-vol)', max: 25 },
]

function overallColour(score: number): string {
  if (score >= 80) return 'var(--pnl-up)'
  if (score >= 60) return 'var(--status-warning)'
  return 'var(--pnl-down)'
}

export function HealthScoreCard({ health, className }: HealthScoreCardProps) {
  const score = health?.score ?? 0
  const color = overallColour(score)

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Health Score</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <div className="flex items-baseline justify-between mb-2">
          <span className="mono text-[22px] font-bold" style={{ color }}>
            {health ? score.toFixed(0) : '—'}
          </span>
          <span className="text-[10px] text-[var(--text-3)] mono">/ 100</span>
        </div>
        {/* Stacked bar */}
        <div
          className="flex h-2 rounded-[2px] overflow-hidden bg-[var(--bg-2)]"
          aria-label="Health score breakdown"
        >
          {SEGMENT_META.map((seg) => {
            const value = health?.[seg.key] ?? 0
            return (
              <div
                key={seg.key}
                className="h-full"
                style={{
                  width: `${value}%`,
                  backgroundColor: seg.color,
                  opacity: 0.9,
                }}
                title={`${seg.label}: ${value}/${seg.max}`}
              />
            )
          })}
        </div>
        {/* Legend */}
        <div className="mt-2 grid grid-cols-2 gap-1">
          {SEGMENT_META.map((seg) => {
            const value = health?.[seg.key] ?? 0
            return (
              <div key={seg.key} className="flex items-center gap-1.5">
                <span
                  className="h-1.5 w-1.5 rounded-full shrink-0"
                  style={{ backgroundColor: seg.color }}
                />
                <span className="text-[10px] text-[var(--text-2)] truncate">
                  {seg.label}
                </span>
                <span className="mono text-[10px] text-[var(--text-1)] ml-auto">
                  {value}/{seg.max}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
