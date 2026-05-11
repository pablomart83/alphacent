import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'
import { usePipelineCounts } from '@/pages/command/useCommandData'
import type { PipelineCounts } from '@/pages/command/StrategyPipelineCounts'

/**
 * PipelineFunnelPanel — horizontal funnel showing the strategy pipeline
 * health: Proposed → Backtested → Paper → Live with counts and conversion
 * rates. Answers "is the pipeline healthy?" without leaving Research.
 *
 * Clicking a stage navigates to Strategies/Library filtered to that status.
 */

const STAGES: Array<{
  key: keyof PipelineCounts
  label: string
  color: string
  filter: string
}> = [
  { key: 'proposed', label: 'Proposed', color: 'var(--text-2)', filter: 'PROPOSED' },
  { key: 'backtested', label: 'Backtested', color: 'var(--status-warning)', filter: 'BACKTESTED' },
  { key: 'paper', label: 'Paper', color: 'var(--accent-secondary)', filter: 'PAPER' },
  { key: 'live', label: 'Live', color: 'var(--pnl-up)', filter: 'LIVE' },
]

export function PipelineFunnelPanel() {
  const navigate = useNavigate()
  const pipeline = usePipelineCounts()
  const counts = pipeline.counts
  const loading = pipeline.isLoading

  const maxCount = Math.max(
    counts.proposed,
    counts.backtested,
    counts.paper,
    counts.live,
    1,
  )

  return (
    <section className="space-y-1.5">
      <SectionLabel>Strategy pipeline health</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-3">
        <div className="grid grid-cols-4 gap-2">
          {STAGES.map((stage, idx) => {
            const count = counts[stage.key]
            const prev = idx > 0 ? counts[STAGES[idx - 1].key] : null
            const convRate =
              prev != null && prev > 0 ? Math.round((count / prev) * 100) : null
            const barPct = Math.round((count / maxCount) * 100)

            return (
              <button
                key={stage.key}
                type="button"
                onClick={() =>
                  navigate(`/strategies/library?status=${stage.filter}`)
                }
                className="flex flex-col gap-1.5 text-left hover:bg-[var(--bg-hover)] rounded-[3px] p-2 transition-colors"
              >
                <div className="flex items-center justify-between">
                  <span
                    className="text-[9px] uppercase tracking-wider font-medium"
                    style={{ color: stage.color }}
                  >
                    {stage.label}
                  </span>
                  {convRate != null && (
                    <span
                      className={cn(
                        'text-[9px] mono',
                        convRate >= 50
                          ? 'text-[var(--pnl-up)]'
                          : convRate >= 20
                            ? 'text-[var(--status-warning)]'
                            : 'text-[var(--pnl-down)]',
                      )}
                    >
                      {convRate}%
                    </span>
                  )}
                </div>
                <div
                  className="mono tabular-nums text-[20px] font-bold"
                  style={{ color: loading ? 'var(--text-3)' : stage.color }}
                >
                  {loading ? '…' : count}
                </div>
                <div className="h-1.5 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
                  <div
                    className="h-full rounded-[1px] transition-all"
                    style={{
                      width: `${barPct}%`,
                      backgroundColor: stage.color,
                    }}
                  />
                </div>
              </button>
            )
          })}
        </div>
        <div className="mt-2 pt-2 border-t border-[var(--border-subtle)] flex items-center gap-3 text-[9px] text-[var(--text-3)]">
          <span>Conversion rates show stage-to-stage pass rate</span>
          <span className="ml-auto">Click any stage to filter the library</span>
        </div>
      </div>
    </section>
  )
}
