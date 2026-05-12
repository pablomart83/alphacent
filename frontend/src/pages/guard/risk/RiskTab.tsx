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
    <div className="h-full overflow-y-auto bg-[var(--bg-0)] px-3 py-3 space-y-5">
      <div className="shrink-0">
        <PerStrategyRiskTable metrics={metrics.data} loading={metrics.isLoading} />
      </div>
      <div className="shrink-0">
        <RiskScoreTrendChart data={history.data} loading={history.isLoading} />
      </div>
      <div className="shrink-0">
        <PositionRiskTable rows={positions.data} loading={positions.isLoading} />
      </div>
      <div className="shrink-0">
        <ExposurePanel
          sector={advanced.data?.sector_exposure}
          assetClass={advanced.data?.asset_class_exposure}
          directional={advanced.data?.directional_exposure}
          loading={advanced.isLoading}
        />
      </div>
      <div className="shrink-0">
        <CorrelationHeatmap
          pairs={advanced.data?.correlated_pairs}
          loading={advanced.isLoading}
        />
      </div>
    </div>
  )
}
