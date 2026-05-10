import { useMemo, useState } from 'react'
import { Filter } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  ErrorState,
  EmptyState,
} from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import {
  useGraduationFunnel,
  type FunnelStage,
} from '../useStrategiesData'

/**
 * SignalFunnel — end-to-end funnel from the unified `signal_decisions`
 * taxonomy. Visualises drop-off between the stages that decide whether
 * a proposal becomes a filled order.
 *
 * Primary path: proposed → wf_validated → activated → signal_emitted →
 * order_submitted → order_filled. Secondary stages (wf_rejected,
 * gate_blocked, rejected_act, order_failed) are displayed underneath as
 * "drops" that explain where strategies fell out.
 */

const PRIMARY_STAGES: Array<{ key: string; label: string; color: string }> = [
  { key: 'proposed', label: 'Proposed', color: 'var(--text-1)' },
  { key: 'wf_validated', label: 'WF validated', color: 'var(--accent-secondary)' },
  { key: 'activated', label: 'Activated', color: 'var(--accent-primary)' },
  { key: 'signal_emitted', label: 'Signal emitted', color: 'var(--accent-ticker)' },
  { key: 'order_submitted', label: 'Submitted', color: 'var(--status-warning)' },
  { key: 'order_filled', label: 'Filled', color: 'var(--pnl-up)' },
]

const REJECTION_STAGES: Array<{ key: string; label: string; description: string }> = [
  { key: 'wf_rejected', label: 'WF rejected', description: 'Failed walk-forward validation' },
  { key: 'rejected_act', label: 'Activation rejected', description: 'Did not clear activation thresholds' },
  { key: 'gate_blocked', label: 'Gate blocked', description: 'Signal-time gates (VIX / trend / market hours)' },
  { key: 'order_failed', label: 'Order failed', description: 'Submission failed' },
]

const LOOKBACK_OPTIONS = [1, 3, 7, 14, 30, 60, 90] as const
type Lookback = (typeof LOOKBACK_OPTIONS)[number]

interface SignalFunnelProps {
  className?: string
}

export function SignalFunnel({ className }: SignalFunnelProps) {
  const [lookback, setLookback] = useState<Lookback>(7)
  const query = useGraduationFunnel(lookback)

  const { primary, rejections, proposedCount } = useMemo(() => {
    const funnel: FunnelStage[] = query.data?.funnel ?? []
    const byStage = new Map(funnel.map((s) => [s.stage, s.count]))

    const primary = PRIMARY_STAGES.map((s) => ({
      ...s,
      count: byStage.get(s.key) ?? 0,
    }))
    const proposedCount = primary[0]?.count ?? 0
    const rejections = REJECTION_STAGES.map((s) => ({
      ...s,
      count: byStage.get(s.key) ?? 0,
    }))
    return { primary, rejections, proposedCount }
  }, [query.data])

  const hasData = proposedCount > 0

  return (
    <section className={cn('flex flex-col gap-2 p-2', className)}>
      <div className="flex items-center gap-2">
        <SectionLabel>Signal funnel</SectionLabel>
        <div className="ml-auto inline-flex items-center gap-1">
          <Filter className="h-3 w-3 text-[var(--text-3)]" />
          <Select
            value={String(lookback)}
            onValueChange={(v) => setLookback(Number(v) as Lookback)}
          >
            <SelectTrigger size="sm" className="h-7 w-[110px] text-[11px]">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {LOOKBACK_OPTIONS.map((n) => (
                <SelectItem key={n} value={String(n)}>
                  {n === 1 ? '24 hours' : `${n} days`}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      {query.isError ? (
        <ErrorState
          title="Couldn't load funnel"
          message={classifyError(query.error, 'signal funnel').message}
          onRetry={() => query.refetch()}
        />
      ) : query.isLoading ? (
        <Skeleton className="h-64 w-full" />
      ) : !hasData ? (
        <EmptyState
          title="No signal decisions in this window"
          description="Widen the lookback window or trigger a cycle to populate the funnel."
        />
      ) : (
        <div className="flex flex-col gap-2">
          {/* Primary path — vertical funnel */}
          <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
            <div className="flex flex-col gap-1">
              {primary.map((stage, idx) => {
                const prev = idx > 0 ? primary[idx - 1].count : proposedCount
                const pctOfProposed = proposedCount > 0 ? (stage.count / proposedCount) * 100 : 0
                const dropFromPrev = prev > 0 ? ((prev - stage.count) / prev) * 100 : 0
                return (
                  <div key={stage.key}>
                    <FunnelBar
                      label={stage.label}
                      count={stage.count}
                      pctOfProposed={pctOfProposed}
                      color={stage.color}
                    />
                    {idx < primary.length - 1 && stage.count > 0 && (
                      <div className="pl-[140px] pr-2 mt-0.5 mb-0.5">
                        <span className="text-[9px] mono text-[var(--text-3)]">
                          -{Math.max(0, dropFromPrev).toFixed(0)}% drop
                        </span>
                      </div>
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Rejection buckets */}
          {rejections.some((r) => r.count > 0) && (
            <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
              <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">
                Rejections
              </div>
              <div className="grid grid-cols-2 gap-x-3 gap-y-1">
                {rejections.map((r) => (
                  <div
                    key={r.key}
                    className="flex items-center gap-2 text-[11px]"
                    title={r.description}
                  >
                    <span className="h-1.5 w-1.5 rounded-full bg-[var(--pnl-down)] shrink-0" />
                    <span className="text-[var(--text-2)] truncate">{r.label}</span>
                    <span className="mono text-[var(--text-1)] ml-auto">
                      {r.count.toLocaleString('en-US')}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}

function FunnelBar({
  label,
  count,
  pctOfProposed,
  color,
}: {
  label: string
  count: number
  pctOfProposed: number
  color: string
}) {
  const width = Math.max(2, Math.min(100, pctOfProposed))
  return (
    <div className="flex items-center gap-2 text-[11px]">
      <span className="w-[130px] text-[var(--text-2)] truncate" title={label}>
        {label}
      </span>
      <div className="flex-1 h-4 rounded-[2px] bg-[var(--bg-0)] overflow-hidden relative">
        <div
          className="h-full transition-all"
          style={{ width: `${width}%`, backgroundColor: color }}
        />
        {width < 15 && count > 0 && (
          <span className="absolute inset-y-0 right-1 flex items-center mono text-[10px] text-[var(--text-1)]">
            {count.toLocaleString('en-US')}
          </span>
        )}
        {width >= 15 && (
          <span className="absolute inset-y-0 left-1.5 flex items-center mono text-[10px] text-white font-medium mix-blend-difference">
            {count.toLocaleString('en-US')}
          </span>
        )}
      </div>
      <span className="w-[44px] text-right mono text-[var(--text-3)] text-[10px]">
        {pctOfProposed >= 1 ? `${pctOfProposed.toFixed(0)}%` : '<1%'}
      </span>
    </div>
  )
}
