import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useSystemHealth } from '../useGuardData'
import { CircuitBreakerGrid } from './CircuitBreakerGrid'

export function CircuitBreakersTab() {
  const health = useSystemHealth()

  if (health.isError) {
    const info = classifyError(health.error, 'circuit breakers')
    return (
      <ErrorState
        title="Couldn't load circuit breakers"
        message={info.message}
        onRetry={() => health.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-3 py-3">
      <CircuitBreakerGrid health={health.data} loading={health.isLoading} />
    </div>
  )
}
