import { useState } from 'react'
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
import { StrategyDeepDiveDrawer } from './StrategyDeepDiveDrawer'

/**
 * Attribution tab — where did the return come from?
 *   1. Per-strategy attribution table (contribution %, Sharpe, trades).
 *      Clicking a row opens the strategy deep-dive drawer (Item 9).
 *   2. Top-15 strategy contribution bar.
 *   3. Sector attribution — Brinson decomposition.
 */
export function AttributionTab() {
  const period = useResearchStore((s) => s.period)
  const strategyAttr = useStrategyAttribution(period)
  const perfAttr = usePerformanceAttribution(period)
  const [selectedStrategyId, setSelectedStrategyId] = useState<string | null>(null)

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
    <div className="h-full overflow-y-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <div className="shrink-0">
        <PerStrategyAttributionTable
          rows={strategyAttr.data}
          loading={strategyAttr.isLoading}
          onRowClick={(row) => setSelectedStrategyId(row.strategy_id)}
          activeStrategyId={selectedStrategyId}
        />
      </div>
      <div className="shrink-0">
        <StrategyContributionBar
          rows={strategyAttr.data}
          loading={strategyAttr.isLoading}
        />
      </div>
      <div className="shrink-0">
        <SectorAttributionPanel
          data={perfAttr.data}
          loading={perfAttr.isLoading}
          error={perfAttr.isError ? perfAttr.error : null}
          onRetry={() => perfAttr.refetch()}
        />
      </div>
      <StrategyDeepDiveDrawer
        strategyId={selectedStrategyId}
        onClose={() => setSelectedStrategyId(null)}
      />
    </div>
  )
}
