import { useState } from 'react'
import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useStressTests } from '../useResearchData'
import { StressScenarioCard } from './StressScenarioCard'
import { CustomScenarioBuilder } from './CustomScenarioBuilder'

/**
 * Stress tab — how would we have fared in historical shock periods, and
 * how would we fare in a custom shock?
 *
 *   1. Scenario cards: COVID, Lehman, SVB (plus any the backend adds).
 *      Each shows simulated portfolio return vs SPY benchmarked at 100.
 *   2. Custom builder: symbol-shock %, volatility multiplier, correlation
 *      shift, time-horizon → preview impact client-side.
 */
export function StressTab() {
  const stress = useStressTests()
  const [expandedName, setExpandedName] = useState<string | null>(null)

  if (stress.isError) {
    const info = classifyError(stress.error, 'stress tests')
    return (
      <ErrorState
        title="Couldn't load stress tests"
        message={info.message}
        onRetry={() => stress.refetch()}
      />
    )
  }

  const scenarios = stress.data?.scenarios ?? []

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      {stress.data?.message && scenarios.length === 0 && (
        <div className="rounded-[3px] border border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_6%,var(--bg-1))] px-3 py-2 text-[11px] text-[var(--text-1)]">
          {stress.data.message}
        </div>
      )}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-3">
        {scenarios.map((s) => (
          <StressScenarioCard
            key={s.name}
            scenario={s}
            expanded={expandedName === s.name}
            onToggle={() =>
              setExpandedName((prev) => (prev === s.name ? null : s.name))
            }
          />
        ))}
      </div>
      <CustomScenarioBuilder />
    </div>
  )
}
