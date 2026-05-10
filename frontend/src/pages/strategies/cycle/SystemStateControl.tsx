import { useState } from 'react'
import { toast } from 'sonner'
import {
  AlertTriangle,
  Pause,
  Play,
  Square,
  RotateCcw,
  Zap,
} from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn, formatAge } from '@/lib/utils'
import {
  useSystemStateTransition,
  useSystemStatus,
  validTransitions,
  type SystemStateValue,
} from '../useStrategiesData'

/**
 * SystemStateControl — big state pill + transition buttons, only valid
 * transitions are enabled. Matches the backend's system_state_manager
 * finite state machine: STOPPED → ACTIVE, ACTIVE ⇄ PAUSED, EMERGENCY_HALT
 * → (reset) STOPPED.
 */

const STATE_CONFIG: Record<
  SystemStateValue,
  { label: string; variant: 'success' | 'warning' | 'muted' | 'error'; description: string }
> = {
  ACTIVE: {
    label: 'Active',
    variant: 'success',
    description: 'Signals firing, orders submitting.',
  },
  PAUSED: {
    label: 'Paused',
    variant: 'warning',
    description: 'No new signals. Open positions monitored.',
  },
  STOPPED: {
    label: 'Stopped',
    variant: 'muted',
    description: 'Autonomous loop is off. Manual trades only.',
  },
  EMERGENCY_HALT: {
    label: 'Emergency halt',
    variant: 'error',
    description: 'Kill switch fired. Requires reset before resuming.',
  },
}

const ACTION_LABEL: Record<string, string> = {
  start: 'Start',
  pause: 'Pause',
  stop: 'Stop',
  resume: 'Resume',
  reset: 'Reset',
}

const ACTION_ICON: Record<string, React.ComponentType<{ className?: string }>> = {
  start: Play,
  pause: Pause,
  stop: Square,
  resume: Play,
  reset: RotateCcw,
}

export function SystemStateControl() {
  const query = useSystemStatus()
  const transition = useSystemStateTransition()
  const [confirmAction, setConfirmAction] = useState<ReturnType<typeof validTransitions>[number] | null>(
    null,
  )

  const state = query.data?.state
  const config = state ? STATE_CONFIG[state] : null
  const transitions = validTransitions(state)

  const runTransition = async (
    action: ReturnType<typeof validTransitions>[number],
  ) => {
    try {
      const res = await transition.mutateAsync({ action })
      toast.success(`System ${res.state.toLowerCase()} — ${res.message}`)
    } catch (err) {
      notifyError(err, `system ${action}`)
    } finally {
      setConfirmAction(null)
    }
  }

  return (
    <section className="flex flex-col gap-2 p-2">
      <SectionLabel>System state</SectionLabel>

      {query.isLoading ? (
        <Skeleton className="h-20 w-full" />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
          <div className="flex items-start justify-between gap-2 mb-2">
            <div className="flex flex-col">
              <div className="flex items-center gap-1.5">
                {state === 'EMERGENCY_HALT' && (
                  <AlertTriangle className="h-3.5 w-3.5 text-[var(--status-error)]" />
                )}
                {state === 'ACTIVE' && <Zap className="h-3.5 w-3.5 text-[var(--pnl-up)]" />}
                <Badge variant={config?.variant ?? 'muted'} size="lg">
                  {config?.label ?? 'Unknown'}
                </Badge>
              </div>
              <p className="text-[10px] text-[var(--text-2)] mt-1 max-w-[220px]">
                {config?.description ?? '—'}
              </p>
            </div>
            <div className="text-right text-[10px] text-[var(--text-3)]">
              <div>Updated</div>
              <div className="mono">{formatAge(query.data?.timestamp)}</div>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-x-2 gap-y-0.5 text-[10px] text-[var(--text-2)] mb-2">
            <StatRow label="Active strategies" value={query.data?.active_strategies ?? 0} />
            <StatRow label="Open positions" value={query.data?.open_positions ?? 0} />
            <StatRow
              label="Uptime"
              value={formatUptime(query.data?.uptime_seconds ?? 0)}
            />
            <StatRow
              label="Last signal"
              value={
                query.data?.last_signal_generated
                  ? formatAge(query.data.last_signal_generated)
                  : '—'
              }
            />
          </div>

          {query.data?.reason && query.data.reason !== 'OK' && (
            <div className="text-[10px] text-[var(--text-3)] italic truncate mb-2" title={query.data.reason}>
              {query.data.reason}
            </div>
          )}

          <div className="flex items-center gap-1 flex-wrap">
            {transitions.map((action) => {
              const Icon = ACTION_ICON[action]
              const isDestructive = action === 'stop' || action === 'reset'
              return (
                <Button
                  key={action}
                  variant={
                    isDestructive ? 'destructive' : action === 'start' ? 'primary' : 'secondary'
                  }
                  size="sm"
                  onClick={() => setConfirmAction(action)}
                  className="gap-1"
                  loading={transition.isPending}
                >
                  <Icon className="h-3 w-3" />
                  {ACTION_LABEL[action]}
                </Button>
              )
            })}
            {transitions.length === 0 && (
              <span className="text-[10px] text-[var(--text-3)]">No valid transitions</span>
            )}
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={(o) => !o && setConfirmAction(null)}
        title={`${ACTION_LABEL[confirmAction ?? 'start']} autonomous trading`}
        description={transitionDescription(confirmAction, state)}
        confirmLabel={ACTION_LABEL[confirmAction ?? 'start']}
        confirmVariant={
          confirmAction === 'stop' || confirmAction === 'reset' ? 'destructive' : 'primary'
        }
        isLoading={transition.isPending}
        onConfirm={() => {
          if (confirmAction) void runTransition(confirmAction)
        }}
      />
    </section>
  )
}

function StatRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center">
      <span className="text-[var(--text-3)]">{label}</span>
      <span className={cn('mono text-[var(--text-1)] ml-auto')}>{value}</span>
    </div>
  )
}

function formatUptime(seconds: number): string {
  if (!seconds || seconds <= 0) return '—'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h >= 24) return `${Math.floor(h / 24)}d ${h % 24}h`
  if (h >= 1) return `${h}h ${m}m`
  if (m >= 1) return `${m}m`
  return `${Math.round(seconds)}s`
}

function transitionDescription(
  action: ReturnType<typeof validTransitions>[number] | null,
  currentState: SystemStateValue | undefined,
): string {
  if (!action) return ''
  switch (action) {
    case 'start':
      return 'Start the autonomous loop. Signals will begin firing on the scheduled cadence.'
    case 'pause':
      return 'Pause signal generation. Open positions continue to be monitored and can still exit on stops or TP.'
    case 'stop':
      return 'Stop the autonomous loop entirely. Open positions stay open; manual trades only until restart.'
    case 'resume':
      return 'Resume signal generation from paused state.'
    case 'reset':
      return currentState === 'EMERGENCY_HALT'
        ? 'Clear the emergency halt flag. The system returns to STOPPED — start manually when ready.'
        : 'Reset the system state.'
  }
}
