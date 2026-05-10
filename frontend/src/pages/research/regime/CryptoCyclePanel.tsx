import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'
import type { CryptoCycle } from '../useResearchData'

interface CryptoCyclePanelProps {
  data: CryptoCycle | undefined
  loading?: boolean
}

export function CryptoCyclePanel({ data, loading }: CryptoCyclePanelProps) {
  const phase = String(data?.phase ?? '—')
  const days = Number(data?.days_since_halving ?? 0) || 0
  const toNext = Number(data?.days_until_halving ?? 0) || 0
  const rec = String(data?.recommendation ?? '')

  return (
    <Card padding="sm" className="flex flex-col gap-2 min-h-[200px]">
      <SectionLabel className="mb-0">Crypto cycle</SectionLabel>
      {loading && !data ? (
        <div className="flex-1 animate-pulse rounded-[3px] bg-[var(--bg-2)]" />
      ) : (
        <>
          <div>
            <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
              Current phase
            </div>
            <div
              className={cn(
                'text-[15px] font-semibold mt-0.5',
                /bull|accumulation/i.test(phase)
                  ? 'text-[var(--pnl-up)]'
                  : /bear|distribution/i.test(phase)
                    ? 'text-[var(--pnl-down)]'
                    : 'text-[var(--text-0)]',
              )}
            >
              {phase.replace(/_/g, ' ')}
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[10px]">
            <div>
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                Since halving
              </div>
              <div className="mono tabular-nums text-[var(--text-0)]">{days} days</div>
            </div>
            <div>
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                To next halving
              </div>
              <div className="mono tabular-nums text-[var(--text-0)]">{toNext} days</div>
            </div>
          </div>
          {rec && (
            <div className="mt-auto text-[11px] text-[var(--text-1)] border-t border-[var(--border-subtle)] pt-1.5">
              {rec}
            </div>
          )}
        </>
      )}
    </Card>
  )
}
