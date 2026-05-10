import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useRegimeComprehensive } from '../useResearchData'
import { CurrentRegimesGrid } from './CurrentRegimesGrid'
import { PerformanceByRegimeTable } from './PerformanceByRegimeTable'
import { RegimeTransitionsTimeline } from './RegimeTransitionsTimeline'
import { StrategyRegimeHeatmap } from './StrategyRegimeHeatmap'
import { MarketContextPanel } from './MarketContextPanel'
import { CryptoCyclePanel } from './CryptoCyclePanel'
import { CarryRatesPanel } from './CarryRatesPanel'
import { MarketQualityScoreCard } from './MarketQualityScoreCard'

/**
 * Regime tab — "what regime are we in, and what works there?"
 *   1. Per-asset-class current regime grid.
 *   2. Performance-by-regime table.
 *   3. Regime transitions timeline.
 *   4. Strategy × regime heatmap (template rows, regime cols).
 *   5. Market context (FRED macro) · Crypto cycle · Carry rates · MQS.
 */
export function RegimeTab() {
  const regime = useRegimeComprehensive()

  if (regime.isError) {
    const info = classifyError(regime.error, 'regime analysis')
    return (
      <ErrorState
        title="Couldn't load regime data"
        message={info.message}
        onRetry={() => regime.refetch()}
      />
    )
  }

  const data = regime.data

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <CurrentRegimesGrid data={data?.current_regimes} loading={regime.isLoading} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <PerformanceByRegimeTable
          rows={data?.performance_by_regime}
          loading={regime.isLoading}
        />
        <RegimeTransitionsTimeline
          rows={data?.regime_transitions}
          loading={regime.isLoading}
        />
      </div>
      <StrategyRegimeHeatmap
        rows={data?.strategy_regime_performance}
        loading={regime.isLoading}
      />
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
        <MarketContextPanel data={data?.market_context} loading={regime.isLoading} />
        <CryptoCyclePanel data={data?.crypto_cycle} loading={regime.isLoading} />
        <CarryRatesPanel data={data?.carry_rates} loading={regime.isLoading} />
        <MarketQualityScoreCard data={data?.market_quality} loading={regime.isLoading} />
      </div>
    </div>
  )
}
