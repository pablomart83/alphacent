import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Circle, Loader2 } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { Skeleton } from '@/components/primitives'
import { wsManager } from '@/services/websocket'
import { cn, formatAge } from '@/lib/utils'
import { type CycleRunRow } from '../useStrategiesData'

/**
 * CyclePipelineVisual — matches v1 TradingCyclePipeline approach exactly.
 *
 * Uses backend stage keys directly (no mapping layer). Stages turn green
 * when complete, blue when running, grey when pending. State is persisted
 * to localStorage so navigating away and back shows the last cycle state.
 *
 * Backend emits these 8 stage keys (+ cache_warming):
 *   cleanup_retirement → performance_feedback → strategy_proposals →
 *   data_validation → walk_forward_backtesting → strategy_activation →
 *   signal_generation → order_submission
 */

// Match backend CYCLE_STAGES exactly — no mapping
const PIPELINE_STAGES = [
  { key: 'cleanup_retirement',      label: 'Cleanup' },
  { key: 'performance_feedback',    label: 'Feedback' },
  { key: 'strategy_proposals',      label: 'Proposals' },
  { key: 'walk_forward_backtesting',label: 'Walk-fwd' },
  { key: 'strategy_activation',     label: 'Activation' },
  { key: 'signal_generation',       label: 'Signals' },
  { key: 'order_submission',        label: 'Orders' },
] as const

type StageStatus = 'pending' | 'running' | 'complete' | 'error'

interface StageState {
  status: StageStatus
  count: number | null
  error?: string | null
  metrics?: Record<string, unknown>
}

type LiveStages = Record<string, StageState>

const LIVE_KEY = 'alphacent_live_cycle_stages_v2'
const LAST_KEY = 'alphacent_last_cycle_stages_v2'

function loadLive(): LiveStages {
  try {
    const raw = localStorage.getItem(LIVE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw) as LiveStages
    // Only restore if there's a running stage (cycle was in progress when we navigated away)
    const hasRunning = Object.values(parsed).some((s) => s.status === 'running')
    if (hasRunning) return parsed
    return {}
  } catch { return {} }
}

function loadLast(): LiveStages {
  try {
    const raw = localStorage.getItem(LAST_KEY)
    return raw ? JSON.parse(raw) : {}
  } catch { return {} }
}

interface CyclePipelineVisualProps {
  lastCycle: CycleRunRow | null
  isRunning: boolean
  className?: string
}

export function CyclePipelineVisual({ lastCycle, isRunning, className }: CyclePipelineVisualProps) {
  const [liveStages, setLiveStages] = useState<LiveStages>(() => loadLive())
  const [lastStages, setLastStages] = useState<LiveStages>(() => loadLast())
  const [liveCycleId, setLiveCycleId] = useState<string | null>(null)
  const [lastEventAt, setLastEventAt] = useState<string | null>(null)

  // Subscribe to cycle_progress WS events — use backend keys directly
  useEffect(() => {
    const off = wsManager.on('cycle_progress', (raw: unknown) => {
      if (!raw || typeof raw !== 'object') return
      const data = raw as {
        stage?: string
        status?: string
        metrics?: Record<string, unknown>
        error?: string
        cycle_id?: string
        timestamp?: string
      }
      if (!data.stage) return

      const status = normaliseStatus(data.status)
      setLastEventAt(data.timestamp ?? new Date().toISOString())
      if (data.cycle_id) setLiveCycleId(data.cycle_id)

      const stage = data.stage

      setLiveStages((prev) => {
        const next = { ...prev }

        // When a stage starts running or completes, mark all prior stages complete.
        // This handles the case where intermediate events were missed.
        if (status === 'running' || status === 'complete') {
          const currentIdx = PIPELINE_STAGES.findIndex((s) => s.key === stage)
          for (let i = 0; i < currentIdx; i++) {
            const priorKey = PIPELINE_STAGES[i].key
            const prior = next[priorKey]
            if (!prior || prior.status === 'pending' || prior.status === 'running') {
              next[priorKey] = { status: 'complete', count: prior?.count ?? null }
            }
          }
        }

        next[stage] = {
          status,
          count: extractCount(data.metrics) ?? prev[stage]?.count ?? null,
          error: data.error ?? null,
          metrics: data.metrics,
        }

        // Persist live state so navigating away and back shows current progress
        try { localStorage.setItem(LIVE_KEY, JSON.stringify(next)) } catch {}
        return next
      })
    })
    return off
  }, [])

  // Listen for cycle_started to reset, cycle_completed to persist
  useEffect(() => {
    const off = wsManager.on('autonomous_cycle', (data: any) => {
      const event = String(data?.event || '').toLowerCase()
      if (event === 'cycle_started') {
        setLiveStages({})
        setLiveCycleId(null)
        try { localStorage.removeItem(LIVE_KEY) } catch {}
      } else if (event === 'cycle_completed') {
        // Mark any still-running stages as complete
        setLiveStages((prev) => {
          const next = { ...prev }
          for (const key of Object.keys(next)) {
            if (next[key].status === 'running') {
              next[key] = { ...next[key], status: 'complete' }
            }
          }
          // Persist as last completed cycle
          try {
            localStorage.setItem(LAST_KEY, JSON.stringify(next))
            localStorage.removeItem(LIVE_KEY)
          } catch {}
          setLastStages(next)
          return next
        })
      }
    })
    return off
  }, [])

  // When isRunning flips false (cycle ended), keep live state visible for 30s
  useEffect(() => {
    if (!isRunning && Object.keys(liveStages).length > 0) {
      const timer = window.setTimeout(() => {
        setLiveStages({})
        setLiveCycleId(null)
      }, 30_000)
      return () => window.clearTimeout(timer)
    }
  }, [isRunning]) // eslint-disable-line react-hooks/exhaustive-deps

  // Derive display stages: live > last > DB row fallback
  const displayStages = useMemo(() => {
    const source = Object.keys(liveStages).length > 0
      ? liveStages
      : Object.keys(lastStages).length > 0
        ? lastStages
        : deriveFromCycleRow(lastCycle)

    return PIPELINE_STAGES.map((s) => ({
      key: s.key,
      label: s.label,
      ...(source[s.key] ?? { status: 'pending' as StageStatus, count: null }),
    }))
  }, [liveStages, lastStages, lastCycle])

  const anyLive = Object.keys(liveStages).length > 0

  return (
    <section className={cn('flex flex-col gap-2 p-2', className)}>
      <div className="flex items-center gap-2">
        <SectionLabel>Pipeline</SectionLabel>
        {anyLive ? (
          <div className="inline-flex items-center gap-1 text-[10px] text-[var(--accent-primary)]">
            <Loader2 className="h-3 w-3 animate-spin" />
            Cycle running
            {liveCycleId && <span className="mono text-[var(--text-3)]">{liveCycleId.slice(-8)}</span>}
            {lastEventAt && <span className="text-[var(--text-3)]">· {formatAge(lastEventAt)}</span>}
          </div>
        ) : lastCycle ? (
          <span className="text-[10px] text-[var(--text-3)]">
            Last cycle{' '}
            <span className="mono text-[var(--text-2)]">{lastCycle.cycle_id.slice(-8)}</span>
            {' · '}{formatAge(lastCycle.completed_at || lastCycle.started_at)}
          </span>
        ) : (
          <span className="text-[10px] text-[var(--text-3)]">No cycle history</span>
        )}
      </div>

      {lastCycle === null && !anyLive && Object.keys(lastStages).length === 0 ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
          <div
            className="grid items-stretch w-full overflow-x-auto"
            style={{
              gridTemplateColumns: PIPELINE_STAGES
                .flatMap((_, i) => i < PIPELINE_STAGES.length - 1
                  ? ['minmax(64px,1fr)', '24px']
                  : ['minmax(64px,1fr)'])
                .join(' '),
            }}
          >
            {displayStages.map((stage, idx) => {
              const next = displayStages[idx + 1]
              const dropPct = computeDropPct(stage.count, next?.count ?? null)
              return (
                <StagePairFragment
                  key={stage.key}
                  stage={stage}
                  dropPct={idx < displayStages.length - 1 ? dropPct : null}
                />
              )
            })}
          </div>
        </div>
      )}
    </section>
  )
}

function StagePairFragment({
  stage,
  dropPct,
}: {
  stage: { key: string; label: string; status: StageStatus; count: number | null; error?: string | null }
  dropPct: number | null
}) {
  const { bg, border, text, Icon } = stageStyle(stage.status)
  return (
    <>
      {/* Stage pill */}
      <div
        className={cn(
          'relative flex flex-col items-center justify-between rounded-[3px] border px-1 py-1.5 min-w-0 transition-colors duration-300',
          bg, border,
        )}
        title={stage.error || stage.label}
      >
        <div className="flex items-center gap-0.5 mb-0.5 min-w-0 w-full justify-center">
          <Icon
            className={cn('h-3 w-3 shrink-0', stage.status === 'running' && 'animate-spin', text)}
          />
          <span className={cn('text-[9px] uppercase tracking-wider font-medium truncate ml-0.5', text)}>
            {stage.label}
          </span>
        </div>
        <div className={cn('mono tabular-nums text-[13px] font-semibold leading-none', text)}>
          {stage.count != null ? stage.count.toLocaleString('en-US') : '—'}
        </div>
        {stage.error && (
          <span className="absolute top-0.5 right-0.5">
            <AlertCircle className="h-2.5 w-2.5 text-[var(--pnl-down)]" />
          </span>
        )}
      </div>

      {/* Drop connector */}
      {dropPct !== null && (
        <div className="self-center inline-flex flex-col items-center justify-center">
          <div className="h-px w-full bg-[var(--border-subtle)]" />
          {dropPct > 0 && (
            <span
              className="mono text-[8px] mt-0.5 whitespace-nowrap"
              style={{
                color: dropPct >= 80 ? 'var(--pnl-down)' : dropPct >= 50 ? 'var(--status-warning)' : 'var(--text-3)',
              }}
            >
              -{dropPct.toFixed(0)}%
            </span>
          )}
        </div>
      )}
    </>
  )
}

function stageStyle(status: StageStatus): {
  bg: string; border: string; text: string
  Icon: React.ComponentType<{ className?: string }>
} {
  switch (status) {
    case 'running':
      return {
        bg: 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)]',
        border: 'border-[var(--accent-primary)]/60',
        text: 'text-[var(--accent-primary)]',
        Icon: Loader2,
      }
    case 'complete':
      return {
        // Green — matches v1 statusConfig.complete
        bg: 'bg-[color-mix(in_oklab,var(--pnl-up)_12%,transparent)]',
        border: 'border-[var(--pnl-up)]/40',
        text: 'text-[var(--pnl-up)]',
        Icon: CheckCircle2,
      }
    case 'error':
      return {
        bg: 'bg-[color-mix(in_oklab,var(--pnl-down)_10%,transparent)]',
        border: 'border-[var(--pnl-down)]/40',
        text: 'text-[var(--pnl-down)]',
        Icon: AlertCircle,
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
  const k = raw.toLowerCase()
  if (k === 'running' || k === 'in_progress' || k === 'active') return 'running'
  if (k === 'complete' || k === 'completed' || k === 'done' || k === 'success') return 'complete'
  if (k === 'error' || k === 'failed' || k === 'failure') return 'error'
  return 'pending'
}

function extractCount(metrics: Record<string, unknown> | undefined): number | null {
  if (!metrics) return null
  const candidates = [
    'proposed', 'proposals_generated', 'count', 'n',
    'backtested', 'backtest_passed', 'passed',
    'activated', 'signals', 'signals_generated',
    'submitted', 'orders_submitted', 'filled', 'orders_filled',
    'retired', 'strategies_retired', 'cleaned', 'strategies_cleaned',
  ]
  for (const k of candidates) {
    const v = metrics[k]
    if (typeof v === 'number' && Number.isFinite(v)) return v
  }
  return null
}

function deriveFromCycleRow(row: CycleRunRow | null): LiveStages {
  if (!row) return {}
  const complete = (count: number | null): StageState => ({
    status: 'complete',
    count,
  })
  return {
    cleanup_retirement:       complete((row.strategies_cleaned ?? 0) + (row.strategies_retired ?? 0)),
    performance_feedback:     complete(row.trades_analyzed ?? null),
    strategy_proposals:       complete(row.proposals_generated ?? null),
    walk_forward_backtesting: complete(row.backtested ?? null),
    strategy_activation:      complete(row.activated ?? null),
    signal_generation:        complete(row.signals_generated ?? row.orders_submitted ?? null),
    order_submission:         complete(row.orders_submitted ?? null),
  }
}

function computeDropPct(prev: number | null, next: number | null): number | null {
  if (prev == null || next == null || prev <= 0) return null
  const drop = prev - next
  if (drop <= 0) return 0
  return (drop / prev) * 100
}
