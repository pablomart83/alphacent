import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useResearchStore } from '@/stores'
import {
  usePerformanceAttribution,
  useStrategyAttribution,
} from '../useResearchData'
import { PerStrategyAttributionTable } from './PerStrategyAttributionTable'
import { StrategyContributionBar } from './StrategyContributionBar'
import { SectorAttributionPanel } from './SectorAttributionPanel'

/**
 * Attribution tab — where did the return come from?
 *   1. Per-strategy attribution table (contribution %, Sharpe, trades).
 *   2. Top-15 strategy contribution bar.
 *   3. Sector attribution — Brinson decomposition with cumulative stacked
 *      area chart of allocation / selection / interaction effects.
 */
export function AttributionTab() {
  const period = useResearchStore((s) => s.period)
  const strategyAttr = useStrategyAttribution(period)
  const perfAttr = usePerformanceAttribution(period)

  if (strategyAttr.isError) {
    const info = classifyError(strategyAttr.error, 'strategy attribution')
    return (
      <ErrorState
        title="Couldn't load strategy attribution"
        message={info.message}
        onRetry={() => strategyAttr.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <PerStrategyAttributionTable
        rows={strategyAttr.data}
        loading={strategyAttr.isLoading}
      />
      <StrategyContributionBar
        rows={strategyAttr.data}
        loading={strategyAttr.isLoading}
      />
      <SectorAttributionPanel
        data={perfAttr.data}
        loading={perfAttr.isLoading}
        error={perfAttr.isError ? perfAttr.error : null}
        onRetry={() => perfAttr.refetch()}
      />
    </div>
  )
}
