import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useResearchStore } from '@/stores'
import {
  useConvictionDistribution,
  useFundamentalStats,
  useMLStats,
  useTemplatePerformance,
  useTransactionCostSavings,
} from '../useResearchData'
import { FundamentalFilterPanel } from './FundamentalFilterPanel'
import { MLFilterPanel } from './MLFilterPanel'
import { ConvictionDistributionChart } from './ConvictionDistributionChart'
import { TemplatePerformanceTable } from './TemplatePerformanceTable'
import { TransactionCostTile } from './TransactionCostTile'

/**
 * Alpha Edge tab — "where does the edge come from?"
 *   1. Fundamental filter stats: pass rate, failure reasons, per-check hit/miss.
 *   2. ML filter stats: signals in/out, avg confidence, model accuracy.
 *   3. Conviction distribution with 65/74 threshold lines + win-rate overlay.
 *   4. Per-template performance table (sortable by Sharpe).
 *   5. Transaction-cost-savings tile.
 */
export function AlphaEdgeTab() {
  const period = useResearchStore((s) => s.period)
  const fundamental = useFundamentalStats(period)
  const ml = useMLStats(period)
  const conviction = useConvictionDistribution(period)
  const templates = useTemplatePerformance(period)
  const tcs = useTransactionCostSavings(period)

  if (fundamental.isError && ml.isError && conviction.isError) {
    const info = classifyError(fundamental.error, 'alpha edge stats')
    return (
      <ErrorState
        title="Couldn't load Alpha Edge analytics"
        message={info.message}
        onRetry={() => fundamental.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-3">
        <FundamentalFilterPanel
          data={fundamental.data}
          loading={fundamental.isLoading}
        />
        <MLFilterPanel data={ml.data} loading={ml.isLoading} />
        <TransactionCostTile data={tcs.data} loading={tcs.isLoading} />
      </div>
      <ConvictionDistributionChart
        data={conviction.data}
        loading={conviction.isLoading}
      />
      <TemplatePerformanceTable
        rows={templates.data}
        loading={templates.isLoading}
      />
    </div>
  )
}
