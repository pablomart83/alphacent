import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber } from '@/lib/utils'
import type { MarketQuality } from '../useResearchData'

interface MarketQualityScoreCardProps {
  data: MarketQuality | undefined
  loading?: boolean
}

function toneColor(tone: 'up' | 'down' | 'warn' | 'neutral'): string {
  return tone === 'up'
    ? 'var(--pnl-up)'
    : tone === 'down'
      ? 'var(--pnl-down)'
      : tone === 'warn'
        ? 'var(--status-warning)'
        : 'var(--text-0)'
}

export function MarketQualityScoreCard({ data, loading }: MarketQualityScoreCardProps) {
  const score = Number(data?.score ?? 0)
  const grade = String(data?.grade ?? '').toLowerCase()
  const components = data?.components ?? {}
  const tone: 'up' | 'down' | 'warn' | 'neutral' =
    grade === 'high'
      ? 'up'
      : grade === 'choppy'
        ? 'down'
        : score >= 70
          ? 'up'
          : score < 40
            ? 'down'
            : 'warn'

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[200px]">
      <SectionLabel className="mb-0">Market quality score</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">Score</div>
            <div
              className={cn('text-[22px] font-semibold mono tabular-nums leading-none')}
              style={{ color: toneColor(tone) }}
            >
              {formatNumber(score, 0)}
            </div>
            <div
              className="text-[10px] mt-0.5 uppercase tracking-wider"
              style={{ color: toneColor(tone) }}
            >
              {grade || 'normal'}
            </div>
          </div>
          <div className="h-1.5 w-full bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
            <div
              className="h-full"
              style={{
                width: `${Math.max(0, Math.min(100, score))}%`,
                backgroundColor: toneColor(tone),
              }}
            />
          </div>
          <div className="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] mt-auto pt-1 border-t border-[var(--border-subtle)]">
            {Object.entries(components).map(([name, val]) => (
              <div key={name} className="flex items-center justify-between">
                <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                  {name.replace(/_/g, ' ')}
                </span>
                <span className="mono tabular-nums text-[var(--text-1)]">
                  {formatNumber(Number(val), 0)}
                </span>
              </div>
            ))}
          </div>
          {data?.reason && (
            <div className="text-[10px] text-[var(--text-3)] italic">{data.reason}</div>
          )}
        </>
      )}
    </Card>
  )
}
