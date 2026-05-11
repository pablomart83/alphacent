import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Circle, Loader2 } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { wsManager } from '@/services/websocket'
import { cn, formatAge } from '@/lib/utils'
import {
  SPEC_STAGES,
  mapBackendStageToSpec,
  type CycleRunRow,
  type SpecStageId,
} from '../useStrategiesData'

/**
 * CyclePipelineVisual — 9-stage horizontal pipeline for the autonomous
 * cycle. Shows per-stage pass/drop counts, drop-off % between stages,
 * a red X overlay when a stage errored, and highlights the currently
 * running stage in --accent-primary.
 *
 * Data sources:
 *  - Last cycle row (from CycleRunRow) provides counts for a completed
 *    cycle on first render.
 *  - Live WS `cycle_progress` events update the stage status in real time
 *    while a cycle is running.
 *  - The spec stages (SPEC_STAGES) are the visual axis; backend stage keys
 *    are mapped onto them via mapBackendStageToSpec.
 */

type StageStatus = 'pending' | 'running' | 'complete' | 'error' | 'skipped'

interface StageState {
  status: StageStatus
  count: number | null
  error?: string | null
  /** Server-provided per-stage metrics from the WS event. */
  metrics?: Record<string, unknown>
}

interface CyclePipelineVisualProps {
  lastCycle: CycleRunRow | null
  isRunning: boolean
  className?: string
}

export function CyclePipelineVisual({ lastCycle, isRunning, className }: CyclePipelineVisualProps) {
  // Live WS state — keyed by spec stage id
  const [liveStates, setLiveStates] = useState<Record<SpecStageId, StageState>>({} as Record<SpecStageId, StageState>)
  const [liveCycleId, setLiveCycleId] = useState<string | null>(null)
  const [lastEventAt, setLastEventAt] = useState<string | null>(null)

  // Subscribe to cycle_progress WS events
  useEffect(() => {
    const off = wsManager.on('cycle_progress', (raw: unknown) => {
      if (!raw || typeof raw !== 'object') return
      const data = raw as {
        stage?: string
        status?: string
        progress_pct?: number
        metrics?: Record<string, unknown>
        error?: string
        cycle_id?: string
        timestamp?: string
      }
      const stageId = data.stage ? mapBackendStageToSpec(data.stage) : null
      if (!stageId) return

      setLastEventAt(data.timestamp ?? new Date().toISOString())
      if (data.cycle_id) setLiveCycleId(data.cycle_id)

      const status = normaliseStatus(data.status)

      setLiveStates((prev) => {
        const next = { ...prev }

        // Auto-complete all spec stages that come before this one when it
        // starts running. This ensures the pipeline never stays stuck on an
        // earlier stage when the backend has already moved past it.
        if (status === 'running' || status === 'complete') {
          const currentIdx = SPEC_STAGES.findIndex((s) => s.id === stageId)
          for (let i = 0; i < currentIdx; i++) {
            const priorId = SPEC_STAGES[i].id
            const priorState = next[priorId]
            // Only auto-complete if the prior stage isn't already complete/error.
            if (!priorState || priorState.status === 'pending' || priorState.status === 'running') {
              next[priorId] = {
                status: 'complete',
                count: priorState?.count ?? null,
                error: null,
              }
            }
          }
        }

        next[stageId] = {
          status,
          count: extractCount(data.metrics) ?? prev[stageId]?.count ?? null,
          error: data.error ?? null,
          metrics: data.metrics,
        }
        return next
      })
    })
    return off
  }, [])

  // Reset live state when a new cycle starts (cycle_id change).
  useEffect(() => {
    if (!isRunning) {
      setLiveStates({} as Record<SpecStageId, StageState>)
      setLiveCycleId(null)
    }
  }, [isRunning])

  // Derive state per spec stage — live state takes precedence, fallback to
  // last-completed-cycle counts from the DB row.
  const stages = useMemo(() => {
    const completedCounts = deriveCountsFromCycleRow(lastCycle)
    return SPEC_STAGES.map((s) => {
      const live = liveStates[s.id]
      if (live) {
        return {
          ...s,
          status: live.status,
          count: live.count,
          error: live.error ?? null,
        }
      }
      return {
        ...s,
        status: lastCycle?.status === 'error' ? ('error' as StageStatus) : ('complete' as StageStatus),
        count: completedCounts[s.id] ?? null,
        error: null,
      }
    })
  }, [liveStates, lastCycle])

  const anyLive = Object.keys(liveStates).length > 0

  return (
    <section className={cn('flex flex-col gap-2 p-2', className)}>
      <div className="flex items-center gap-2">
        <SectionLabel>Pipeline</SectionLabel>
        {anyLive ? (
          <div className="inline-flex items-center gap-1 text-[10px] text-[var(--accent-primary)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            Cycle {liveCycleId ? <span className="mono">{liveCycleId.slice(-8)}</span> : 'running'}
            {lastEventAt && <span className="text-[var(--text-3)]">· {formatAge(lastEventAt)}</span>}
          </div>
        ) : lastCycle ? (
          <span className="text-[10px] text-[var(--text-3)]">
            Last cycle{' '}
            <span className="mono text-[var(--text-2)]">{lastCycle.cycle_id.slice(-8)}</span> ·{' '}
            {formatAge(lastCycle.completed_at || lastCycle.started_at)}
          </span>
        ) : (
          <span className="text-[10px] text-[var(--text-3)]">No cycle history</span>
        )}
      </div>

      {lastCycle === null && !anyLive ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
          {/* Grid of 9 stages + 8 drops: `1fr 32px 1fr 32px ... 1fr`.
              Stages share the available width equally; drop labels sit
              in fixed-width gaps between them. No horizontal scrolling
              at any viewport wider than the minimum 9 * 72px + 8 * 32px
              ≈ 900px. */}
          <div
            className="grid items-stretch w-full"
            style={{
              gridTemplateColumns: Array(9)
                .fill('minmax(0, 1fr)')
                .flatMap((col, i) => (i < 8 ? [col, '32px'] : [col]))
                .join(' '),
            }}
          >
            {stages.map((stage, idx) => {
              const nextStage = stages[idx + 1]
              const dropPct = computeDropPct(stage.count, nextStage?.count ?? null)
              return (
                <FragmentPair
                  key={stage.id}
                  stage={stage}
                  dropPct={idx < stages.length - 1 ? dropPct : null}
                  showConnector={idx < stages.length - 1}
                />
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}

function FragmentPair({
  stage,
  dropPct,
  showConnector,
}: {
  stage: {
    id: SpecStageId
    label: string
    status: StageStatus
    count: number | null
    error: string | null
  }
  dropPct: number | null
  showConnector: boolean
}) {
  return (
    <>
      <StagePill stage={stage} />
      {showConnector && <DropConnector dropPct={dropPct} />}
    </>
  )
}

function StagePill({ stage }: {
  stage: {
    id: SpecStageId
    label: string
    status: StageStatus
    count: number | null
    error: string | null
  }
}) {
  const { bg, border, text, Icon } = statusStyle(stage.status)
  return (
    <div
      className={cn(
        'relative flex flex-col items-center justify-between rounded-[3px] border px-1.5 py-1.5 min-w-0',
        bg,
        border,
      )}
      title={stage.error || stage.label}
    >
      <div className="flex items-center gap-1 mb-0.5 min-w-0 w-full justify-center">
        <Icon
          className={cn(
            'h-3 w-3 shrink-0',
            stage.status === 'running' && 'animate-spin',
            text,
          )}
        />
        <span className={cn('text-[9px] uppercase tracking-wider font-medium truncate', text)}>
          {stage.label}
        </span>
      </div>
      <div className={cn('mono tabular-nums text-[14px] font-semibold', text)}>
        {stage.count != null ? stage.count.toLocaleString('en-US') : '—'}
      </div>
      {stage.error && (
        <span className="absolute top-1 right-1">
          <AlertCircle className="h-3 w-3 text-[var(--pnl-down)]" />
        </span>
      )}
    </div>
  )
}

function DropConnector({ dropPct }: { dropPct: number | null }) {
  if (dropPct == null) {
    return <div className="self-center h-px bg-[var(--border-subtle)]" />
  }
  const color =
    dropPct >= 80
      ? 'var(--pnl-down)'
      : dropPct >= 50
        ? 'var(--status-warning)'
        : 'var(--text-3)'
  return (
    <div
      className="self-center inline-flex flex-col items-center justify-center px-0.5"
      title={`Drop-off ${dropPct.toFixed(0)}%`}
    >
      <div className="h-px w-full bg-[var(--border-subtle)]" />
      <span
        className="mono text-[9px] mt-0.5 whitespace-nowrap"
        style={{ color }}
      >
        -{dropPct.toFixed(0)}%
      </span>
    </div>
  )
}

function statusStyle(status: StageStatus): {
  bg: string
  border: string
  text: string
  Icon: React.ComponentType<{ className?: string }>
} {
  switch (status) {
    case 'running':
      return {
        bg: 'bg-[color-mix(in_oklab,var(--accent-primary)_12%,transparent)]',
        border: 'border-[var(--accent-primary)]/50',
        text: 'text-[var(--accent-primary)]',
        Icon: Loader2,
      }
    case 'complete':
      return {
        bg: 'bg-[var(--bg-2)]',
        border: 'border-[var(--border-subtle)]',
        text: 'text-[var(--text-0)]',
        Icon: CheckCircle2,
      }
    case 'error':
      return {
        bg: 'bg-[color-mix(in_oklab,var(--pnl-down)_10%,transparent)]',
        border: 'border-[var(--pnl-down)]/40',
        text: 'text-[var(--pnl-down)]',
        Icon: AlertCircle,
      }
    case 'skipped':
      return {
        bg: 'bg-[var(--bg-2)]',
        border: 'border-[var(--border-subtle)]',
        text: 'text-[var(--text-3)]',
        Icon: Circle,
      }
    case 'pending':
    default:
      return {
        bg: 'bg-[var(--bg-1)]',
        border: 'border-[var(--border-subtle)]',
        text: 'text-[var(--text-3)]',
        Icon: Circle,
      }
  }
}

function normaliseStatus(raw: string | undefined): StageStatus {
  if (!raw) return 'pending'
  const key = raw.toLowerCase()
  if (key === 'running' || key === 'in_progress' || key === 'active') return 'running'
  if (key === 'complete' || key === 'completed' || key === 'done' || key === 'success') return 'complete'
  if (key === 'error' || key === 'failed' || key === 'failure') return 'error'
  if (key === 'skipped' || key === 'noop') return 'skipped'
  return 'pending'
}

function extractCount(metrics: Record<string, unknown> | undefined): number | null {
  if (!metrics) return null
  // Common count-like keys emitted by the backend.
  const candidates = [
    'count',
    'n',
    'proposals',
    'proposals_generated',
    'activated',
    'signals',
    'signals_generated',
    'backtested',
    'backtest_passed',
    'submitted',
    'orders_submitted',
    'filled',
    'orders_filled',
    'retired',
    'strategies_retired',
    'cleaned',
    'strategies_cleaned',
  ]
  for (const k of candidates) {
    const v = metrics[k]
    if (typeof v === 'number' && Number.isFinite(v)) return v
  }
  return null
}

function deriveCountsFromCycleRow(row: CycleRunRow | null): Record<SpecStageId, number | null> {
  const base: Record<SpecStageId, number | null> = {
    cleanup: null,
    market_analysis: null,
    proposal: null,
    walk_forward: null,
    monte_carlo: null,
    direction_aware: null,
    conviction: null,
    activation: null,
    signal_generation: null,
  }
  if (!row) return base

  base.cleanup = row.strategies_cleaned + row.strategies_retired
  base.market_analysis = row.symbols_checked || row.symbols_passed
  base.proposal = row.proposals_generated
  base.walk_forward = row.backtested
  base.monte_carlo = row.backtest_passed
  // Direction-aware + conviction aren't individually tracked on the cycle row;
  // use backtest_passed as the best available upper bound (each row flows
  // through both filters). When signal_decisions data is richer we can refine.
  base.direction_aware = row.backtest_passed
  base.conviction = row.activated
  base.activation = row.activated
  base.signal_generation = row.signals_generated || row.orders_submitted
  return base
}

function computeDropPct(prev: number | null, next: number | null): number | null {
  if (prev == null || next == null || prev <= 0) return null
  const drop = prev - next
  if (drop <= 0) return 0
  return (drop / prev) * 100
}
