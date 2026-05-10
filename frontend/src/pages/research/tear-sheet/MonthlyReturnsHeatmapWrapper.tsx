import { MonthlyReturnsHeatmap } from '../performance/MonthlyReturnsHeatmap'
import type { MonthlyReturn } from '../useResearchData'

interface WrapperProps {
  rows: MonthlyReturn[] | undefined
  loading?: boolean
}

/** Reuses the Performance-tab heatmap with the tear-sheet's monthly_returns payload. */
export function MonthlyReturnsHeatmapWrapper({ rows, loading }: WrapperProps) {
  return <MonthlyReturnsHeatmap entries={rows ?? []} loading={loading} />
}
