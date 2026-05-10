import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  AlertOctagon,
  CheckCircle2,
  CircuitBoard,
  PauseCircle,
  RefreshCw,
} from 'lucide-react'
import {
  Button,
  ConfirmDialog,
  EmptyState,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import {
  useResetCircuitBreaker,
  type SystemHealthPayload,
  type CircuitBreakerEntry,
} from '../useGuardData'

interface CircuitBreakerGridProps {
  health: SystemHealthPayload | null | undefined
  loading?: boolean
}

/**
 * CircuitBreakerGrid — one card per /control/system-health.circuit_breakers[]
 * entry. Per-CB timeline chart (spec mentions 24h state transitions) is not
 * available from the backend yet — we surface a scoped note next to the
 * Sprint 9 reset action instead of inventing state.
 *
 * Reset currently goes via POST /control/circuit-breaker/reset which resets
 * the RiskManager-level circuit, not per-category CBs. That's all the
 * backend exposes today; called out honestly in the card footer.
 */
export function CircuitBreakerGrid({ health, loading }: CircuitBreakerGridProps) {
  const [confirmOpen, setConfirmOpen] = useState(false)
  const reset = useResetCircuitBreaker()

  const sorted = useMemo(() => {
    const list = (health?.circuit_breakers ?? []) as unknown as CircuitBreakerEntry[]
    return list.slice().sort((a, b) => {
      const ord = (cb: CircuitBreakerEntry) =>
        cb.state === 'OPEN' ? 0 : cb.state === 'HALF_OPEN' ? 1 : 2
      return ord(a) - ord(b)
    })
  }, [health])

  const handleReset = async () => {
    try {
      await reset.mutateAsync()
      toast.success('Circuit breaker reset')
      setConfirmOpen(false)
    } catch (err) {
      notifyError(err, 'reset circuit breaker')
    }
  }

  if (loading && !health) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[120px]" />
        ))}
      </div>
    )
  }

  if (!sorted.length) {
    return (
      <EmptyState
        icon={CircuitBoard}
        title="No circuit breakers reported"
        description="The backend exposes circuit_breakers[] on /control/system-health — empty means nothing has tripped."
      />
    )
  }

  const hasOpen = sorted.some((cb) => cb.state === 'OPEN')

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel className="mb-0">
          Circuit breakers · {sorted.length}
        </SectionLabel>
        <Button
          size="sm"
          variant={hasOpen ? 'primary' : 'secondary'}
          onClick={() => setConfirmOpen(true)}
          className="gap-1.5"
          disabled={reset.isPending}
        >
          <RefreshCw className="h-3 w-3" />
          Reset global breaker
        </Button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {sorted.map((cb) => (
          <BreakerCard key={cb.category} cb={cb} />
        ))}
      </div>

      <p className="text-[9px] text-[var(--text-3)] uppercase tracking-wider mt-1">
        Reset targets the RiskManager-level breaker. Per-API (eToro / Yahoo / FMP)
        resets require a backend extension — flag before Sprint 10 if the CIO needs
        them surfaced individually.
      </p>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Reset circuit breaker"
        description="Clears the RiskManager-level breaker so new signals can fire. Use only when you've confirmed the upstream cause (stale data, API outage) is resolved."
        confirmLabel="Reset"
        confirmVariant="primary"
        isLoading={reset.isPending}
        onConfirm={handleReset}
      />
    </div>
  )
}

function BreakerCard({ cb }: { cb: CircuitBreakerEntry }) {
  const state = cb.state || 'CLOSED'
  const color =
    state === 'OPEN'
      ? 'var(--pnl-down)'
      : state === 'HALF_OPEN'
        ? 'var(--status-warning)'
        : 'var(--pnl-up)'
  const Icon =
    state === 'OPEN' ? AlertOctagon : state === 'HALF_OPEN' ? PauseCircle : CheckCircle2

  return (
    <article
      className={cn(
        'rounded-[3px] border bg-[var(--bg-1)] p-2 flex flex-col gap-1.5',
      )}
      style={{
        borderColor:
          state === 'OPEN' ? color : 'var(--border-subtle)',
        boxShadow:
          state === 'OPEN'
            ? `0 0 0 1px color-mix(in oklab, ${color} 40%, transparent)`
            : undefined,
      }}
    >
      <header className="flex items-start justify-between gap-2">
        <span className="text-[11px] font-semibold text-[var(--text-0)] uppercase tracking-wider truncate">
          {cb.category}
        </span>
        <span
          className={cn(
            'inline-flex items-center gap-1 px-1.5 h-[18px] rounded-[3px] text-[9px] font-semibold uppercase tracking-wider',
            state === 'OPEN' && 'animate-pulse',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${color} 15%, transparent)`,
            color,
            border: `1px solid color-mix(in oklab, ${color} 40%, transparent)`,
          }}
        >
          <Icon className="h-3 w-3" />
          {state.replace('_', ' ')}
        </span>
      </header>
      <div className="grid grid-cols-2 gap-1 text-[10px]">
        <Cell label="Failures" value={cb.failure_count.toString()} />
        <Cell
          label="Cooldown"
          value={
            cb.cooldown_remaining_seconds > 0
              ? `${cb.cooldown_remaining_seconds.toFixed(0)}s`
              : '—'
          }
        />
      </div>
    </article>
  )
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline justify-between gap-1">
      <span className="text-[var(--text-3)] uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span className="mono tabular-nums text-[var(--text-1)]">{value}</span>
    </div>
  )
}
