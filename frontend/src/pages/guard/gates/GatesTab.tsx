import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useSystemHealth } from '../useGuardData'
import { GateStatusGrid } from './GateStatusGrid'

/**
 * GatesTab — one card per trading gate from /control/system-health.trading_gates[].
 * Cards are sorted so blocking gates float to the top and pulse.
 */
export function GatesTab() {
  const health = useSystemHealth()

  if (health.isError) {
    const info = classifyError(health.error, 'system health')
    return (
      <ErrorState
        title="Couldn't load gates"
        message={info.message}
        onRetry={() => health.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-3 py-3">
      <GateStatusGrid gates={health.data?.trading_gates} loading={health.isLoading} />
    </div>
  )
}
