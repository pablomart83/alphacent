import {
  AlertTriangle,
  Check,
  CheckCircle2,
  Hourglass,
  Target,
  TrendingDown,
  TrendingUp,
  X,
} from 'lucide-react'
import { EmptyState, Skeleton } from '@/components/primitives'
import { cn, formatTimestamp } from '@/lib/utils'
import { useTradeLifecycle } from '../useGuardData'

interface TradeLifecycleChainProps {
  tradeId: string | null
}

/**
 * TradeLifecycleChain — vertical timeline of the steps from signal to close
 * for a single trade. Uses /audit/trade-lifecycle/{id}.
 */
export function TradeLifecycleChain({ tradeId }: TradeLifecycleChainProps) {
  const query = useTradeLifecycle(tradeId)

  if (!tradeId) return null

  if (query.isLoading) {
    return <Skeleton className="h-24 w-full" />
  }

  if (query.isError) {
    return (
      <p className="text-[10px] text-[var(--pnl-down)]">
        Couldn't load trade lifecycle: {String((query.error as Error)?.message ?? 'unknown')}
      </p>
    )
  }

  const data = query.data
  if (!data) {
    return (
      <EmptyState
        title="No lifecycle data"
        description="This trade has no linked lifecycle chain."
        className="py-4"
      />
    )
  }

  const steps = data.steps ?? []

  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <div className="flex items-baseline gap-2 mb-2">
        <span className="mono text-[11px] text-[var(--text-0)] font-medium">
          {data.symbol ?? data.trade_id}
        </span>
        {data.strategy_name && (
          <span
            className="text-[10px] text-[var(--text-3)] truncate"
            title={data.strategy_name}
          >
            {data.strategy_name}
          </span>
        )}
      </div>

      {steps.length === 0 ? (
        <p className="text-[10px] text-[var(--text-3)]">No lifecycle steps recorded.</p>
      ) : (
        <ol className="space-y-1.5 relative">
          {steps.map((s, i) => {
            const Icon = iconForStep(s.step)
            const color = colorForStep(s.step)
            const details = Object.entries(s.details ?? {}).slice(0, 4)
            return (
              <li key={`${s.step}-${i}`} className="flex gap-2">
                <div className="relative flex flex-col items-center">
                  <div
                    className={cn(
                      'h-5 w-5 rounded-full flex items-center justify-center shrink-0',
                    )}
                    style={{
                      backgroundColor: `color-mix(in oklab, ${color} 15%, transparent)`,
                      border: `1px solid color-mix(in oklab, ${color} 40%, transparent)`,
                      color,
                    }}
                  >
                    <Icon className="h-3 w-3" />
                  </div>
                  {i < steps.length - 1 && (
                    <div className="w-[1px] flex-1 bg-[var(--border-subtle)] my-0.5" />
                  )}
                </div>
                <div className="flex-1 min-w-0 pb-1.5">
                  <div className="flex items-baseline gap-2">
                    <span className="text-[11px] font-medium text-[var(--text-0)] capitalize">
                      {s.step.replace(/_/g, ' ')}
                    </span>
                    <span className="text-[9px] text-[var(--text-3)] mono tabular-nums">
                      {formatTimestamp(s.timestamp, 'long') || '—'}
                    </span>
                  </div>
                  {details.length > 0 && (
                    <dl className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-0.5 text-[10px]">
                      {details.map(([k, v]) => (
                        <div key={k} className="flex items-baseline gap-1 min-w-0">
                          <dt className="text-[9px] uppercase tracking-wider text-[var(--text-3)] shrink-0">
                            {k}
                          </dt>
                          <dd
                            className="mono tabular-nums text-[var(--text-1)] truncate"
                            title={String(v)}
                          >
                            {String(v)}
                          </dd>
                        </div>
                      ))}
                    </dl>
                  )}
                </div>
              </li>
            )
          })}
        </ol>
      )}
    </div>
  )
}

function iconForStep(step: string): React.ComponentType<{ className?: string }> {
  const s = step.toLowerCase()
  if (s.includes('signal')) return TrendingUp
  if (s.includes('order')) return Target
  if (s.includes('fill')) return Check
  if (s.includes('trailing') || s.includes('stop')) return AlertTriangle
  if (s.includes('close') || s.includes('exit')) return TrendingDown
  if (s.includes('rejected') || s.includes('failed')) return X
  if (s.includes('wait') || s.includes('pending')) return Hourglass
  return CheckCircle2
}

function colorForStep(step: string): string {
  const s = step.toLowerCase()
  if (s.includes('rejected') || s.includes('failed')) return 'var(--pnl-down)'
  if (s.includes('trailing') || s.includes('stop')) return 'var(--status-warning)'
  if (s.includes('close') || s.includes('exit')) return 'var(--text-1)'
  if (s.includes('fill') || s.includes('filled')) return 'var(--pnl-up)'
  return 'var(--accent-primary)'
}
