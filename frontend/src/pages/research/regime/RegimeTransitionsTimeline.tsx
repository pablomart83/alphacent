import { SectionLabel } from '@/components/layout'
import { Badge, EmptyState } from '@/components/primitives'
import { History } from 'lucide-react'
import { formatTimestamp } from '@/lib/utils'
import type { RegimeTransition } from '../useResearchData'

interface RegimeTransitionsTimelineProps {
  rows: RegimeTransition[] | undefined
  loading?: boolean
}

export function RegimeTransitionsTimeline({
  rows,
  loading,
}: RegimeTransitionsTimelineProps) {
  const data = rows ?? []

  if (loading && !data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Recent transitions</SectionLabel>
        <div className="h-[220px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            From config/autonomous_trading.yaml
          </span>
        }
      >
        Recent transitions
      </SectionLabel>
      {data.length === 0 ? (
        <EmptyState
          icon={History}
          title="No regime transitions recorded"
          description="Transitions appear once the market_regime section of autonomous_trading.yaml updates."
          className="py-6"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-3 py-2 space-y-2">
          {data.map((t, i) => (
            <div key={i} className="flex items-center gap-2 text-[11px]">
              <span className="mono tabular-nums text-[var(--text-3)] w-[120px] shrink-0">
                {t.date ? formatTimestamp(t.date, 'short') : '—'}
              </span>
              {t.from_regime ? (
                <>
                  <Badge variant="default">{t.from_regime}</Badge>
                  <span className="text-[var(--text-3)]">→</span>
                </>
              ) : null}
              <Badge
                variant={
                  /up/i.test(t.to_regime)
                    ? 'regime-up'
                    : /down/i.test(t.to_regime)
                      ? 'regime-down'
                      : /range/i.test(t.to_regime)
                        ? 'regime-range'
                        : 'default'
                }
              >
                {t.to_regime || '—'}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}
