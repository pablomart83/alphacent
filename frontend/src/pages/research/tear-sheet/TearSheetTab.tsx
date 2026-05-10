import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import { useResearchStore } from '@/stores'
import { useTearSheet } from '../useResearchData'
import { UnderwaterPlot } from './UnderwaterPlot'
import { WorstDrawdownsTable } from './WorstDrawdownsTable'
import { ReturnDistributionPanel } from './ReturnDistributionPanel'
import { AnnualReturnsGrid } from './AnnualReturnsGrid'
import { MonthlyReturnsHeatmapWrapper } from './MonthlyReturnsHeatmapWrapper'

/**
 * Tear Sheet tab — institutional-grade dossier on risk and returns.
 *   1. Underwater plot (Visx) — drawdown ribbon over time.
 *   2. Worst-drawdowns table — rank, start/trough/recovery, depth, duration.
 *   3. Return distribution histogram + skew/kurtosis/vol numbers.
 *   4. Annual returns grid (one tile per year).
 *   5. Monthly returns heatmap — reuses the Performance tab component.
 */
export function TearSheetTab() {
  const period = useResearchStore((s) => s.period)
  const sheet = useTearSheet(period)

  if (sheet.isError) {
    const info = classifyError(sheet.error, 'tear sheet')
    return (
      <ErrorState
        title="Couldn't load tear sheet"
        message={info.message}
        onRetry={() => sheet.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)] px-3 py-3 space-y-4">
      <UnderwaterPlot
        points={sheet.data?.underwater_plot}
        loading={sheet.isLoading}
      />
      <WorstDrawdownsTable
        rows={sheet.data?.worst_drawdowns}
        loading={sheet.isLoading}
      />
      <ReturnDistributionPanel
        bins={sheet.data?.return_distribution}
        skew={sheet.data?.skew}
        kurtosis={sheet.data?.kurtosis}
        loading={sheet.isLoading}
      />
      <AnnualReturnsGrid
        rows={sheet.data?.annual_returns}
        loading={sheet.isLoading}
      />
      <MonthlyReturnsHeatmapWrapper
        rows={sheet.data?.monthly_returns}
        loading={sheet.isLoading}
      />
    </div>
  )
}
