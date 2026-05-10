import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useResearchStore } from '@/stores'
import { useTradeAnalytics } from '../useResearchData'
import { TradeStatTiles } from './TradeStatTiles'
import { WinLossDistributionPie } from './WinLossDistributionPie'
import { HoldingPeriodHistogram } from './HoldingPeriodHistogram'
import { PnLByHourBar } from './PnLByHourBar'
import { PnLByDayOfWeekBar } from './PnLByDayOfWeekBar'
import { TradeSizeDistribution } from './TradeSizeDistribution'

/**
 * Trades tab — the anatomy of every closed position.
 *   1. Stat tiles (total / win / loss counts, avg holding, best/worst,
 *      profit factor).
 *   2. Win-loss pie.
 *   3. Holding-period histogram.
 *   4. P&L by hour-of-day (session shading).
 *   5. P&L by day-of-week.
 *   6. Trade-size distribution.
 */
export function TradesTab() {
  const period = useResearchStore((s) => s.period)
  const trades = useTradeAnalytics(period)

  if (trades.isError) {
    const info = classifyError(trades.error, 'trade analytics')
    return (
      <ErrorState
        title="Couldn't load trade analytics"
        message={info.message}
        onRetry={() => trades.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <TradeStatTiles data={trades.data} loading={trades.isLoading} />
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <WinLossDistributionPie data={trades.data} loading={trades.isLoading} />
        <HoldingPeriodHistogram data={trades.data} loading={trades.isLoading} />
      </div>
      <PnLByHourBar data={trades.data} loading={trades.isLoading} />
      <PnLByDayOfWeekBar data={trades.data} loading={trades.isLoading} />
      <TradeSizeDistribution data={trades.data} loading={trades.isLoading} />
    </div>
  )
}
