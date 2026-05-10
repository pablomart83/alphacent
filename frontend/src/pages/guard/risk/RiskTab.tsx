import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import {
  useAdvancedRisk,
  useRiskHistory,
  useRiskMetrics,
  useRiskPositions,
} from '../useGuardData'
import { PerStrategyRiskTable } from './PerStrategyRiskTable'
import { PositionRiskTable } from './PositionRiskTable'
import { ExposurePanel } from './ExposurePanel'
import { RiskScoreTrendChart } from './RiskScoreTrendChart'
import { CorrelationHeatmap } from './CorrelationHeatmap'

/**
 * RiskTab — right panel of Guard surface. Stacks:
 *   1. Per-strategy VaR contributions
 *   2. 30-day drawdown/leverage trend
 *   3. Position-level risk table
 *   4. Exposures (sector / asset class / directional)
 *   5. Correlation heatmap
 */
export function RiskTab() {
  const metrics = useRiskMetrics()
  const positions = useRiskPositions()
  const history = useRiskHistory('30d')
  const advanced = useAdvancedRisk()

  if (metrics.isError) {
    const info = classifyError(metrics.error, 'risk metrics')
    return (
      <ErrorState
        title="Couldn't load risk metrics"
        message={info.message}
        onRetry={() => metrics.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-3 py-3 space-y-5">
      <PerStrategyRiskTable metrics={metrics.data} loading={metrics.isLoading} />
      <RiskScoreTrendChart data={history.data} loading={history.isLoading} />
      <PositionRiskTable rows={positions.data} loading={positions.isLoading} />
      <ExposurePanel
        sector={advanced.data?.sector_exposure}
        assetClass={advanced.data?.asset_class_exposure}
        directional={advanced.data?.directional_exposure}
        loading={advanced.isLoading}
      />
      <CorrelationHeatmap
        pairs={advanced.data?.correlated_pairs}
        loading={advanced.isLoading}
      />
    </div>
  )
}
