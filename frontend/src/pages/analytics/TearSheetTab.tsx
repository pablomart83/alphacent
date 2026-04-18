import { type FC } from 'react';
import { motion } from 'framer-motion';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { UnderwaterPlot } from '../../components/charts/UnderwaterPlot';
import { ReturnDistribution } from '../../components/charts/ReturnDistribution';
import { MonthlyReturnsHeatmap } from '../../components/charts/MonthlyReturnsHeatmap';
import { SVGBarChart } from '../../components/charts/SVGBarChart';
import { DataSection, ChartSkeleton, TableSkeleton, HeatmapSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatPercentage } from '../../lib/utils';
import { colors } from '../../lib/design-tokens';
import type { TearSheetData } from '../../types/analytics';

interface TearSheetTabProps {
  data: TearSheetData | null;
  loading: boolean;
  error: string | null;
  rMultiples?: any | null;
  onRetry: () => void;
}

export const TearSheetTab: FC<TearSheetTabProps> = ({
  data,
  loading,
  error,
  rMultiples,
  onRetry,
}) => {
  return (
    <DataSection
      isLoading={loading}
      error={error}
      skeleton={
        <>
          <ChartSkeleton height={250} />
          <TableSkeleton rows={5} columns={7} />
          <ChartSkeleton height={250} />
          <ChartSkeleton height={200} />
          <HeatmapSkeleton rows={4} columns={12} />
        </>
      }
      onRetry={onRetry}
    >
      {data ? (
        <>
          {/* Underwater Plot */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Underwater Plot (Drawdown from Peak)</SectionLabel>
              <UnderwaterPlot data={data.underwater_plot} height={280} />
            </div>
          </motion.div>

          {/* Worst Drawdowns Table */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.05 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Worst Drawdowns</SectionLabel>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Rank', 'Start Date', 'Trough Date', 'Recovery Date', 'Depth', 'Duration (days)', 'Recovery (days)'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-xs font-mono text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.worst_drawdowns.map((dd, i) => (
                      <tr key={dd.rank} className={cn('border-b border-border/50', i % 2 === 0 && 'bg-muted/30')}>
                        <td className="px-3 py-2 font-mono font-semibold">{dd.rank}</td>
                        <td className="px-3 py-2 font-mono text-sm">{dd.start_date}</td>
                        <td className="px-3 py-2 font-mono text-sm">{dd.trough_date}</td>
                        <td className="px-3 py-2 font-mono text-sm">{dd.recovery_date ?? '—'}</td>
                        <td className="px-3 py-2 font-mono text-sm text-accent-red">{formatPercentage(dd.depth_pct)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{dd.duration_days}</td>
                        <td className="px-3 py-2 font-mono text-sm">{dd.recovery_days ?? '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>

          {/* Return Distribution */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Return Distribution</SectionLabel>
              <ReturnDistribution
                data={data.return_distribution}
                skew={data.skew}
                kurtosis={data.kurtosis}
                height={280}
              />
            </div>
          </motion.div>

          {/* Cumulative Returns by Year */}
          {data.annual_returns.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.15 }}>
              <div className="border border-border rounded-md p-4">
                <SectionLabel>Cumulative Returns by Year</SectionLabel>
                <SVGBarChart
                  data={data.annual_returns.map((entry) => ({
                    label: String(entry.year),
                    value: entry.return_pct,
                    color: entry.return_pct >= 0 ? colors.green : colors.red,
                  }))}
                  height={250}
                  formatValue={(v: number) => `${v.toFixed(2)}%`}
                />
              </div>
            </motion.div>
          )}

          {/* Monthly Returns Heatmap */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Monthly Returns Heatmap</SectionLabel>
              <MonthlyReturnsHeatmap data={data.monthly_returns} />
            </div>
          </motion.div>

          {/* R-Multiple Distribution (Sprint 7.1) */}
          {rMultiples && !rMultiples.message && rMultiples.buckets?.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.25 }}>
              <div className="border border-border rounded-md p-4">
                <div className="flex items-center justify-between mb-3">
                  <SectionLabel className="mb-0">R-Multiple Distribution</SectionLabel>
                  <div className="flex items-center gap-4 text-xs font-mono text-muted-foreground">
                    <span>Mean R: <span className={cn('font-bold', rMultiples.mean_r >= 0 ? 'text-accent-green' : 'text-accent-red')}>{rMultiples.mean_r >= 0 ? '+' : ''}{rMultiples.mean_r.toFixed(2)}R</span></span>
                    <span>Median R: <span className={cn('font-bold', rMultiples.median_r >= 0 ? 'text-accent-green' : 'text-accent-red')}>{rMultiples.median_r >= 0 ? '+' : ''}{rMultiples.median_r.toFixed(2)}R</span></span>
                    <span>Expectancy: <span className={cn('font-bold', rMultiples.expectancy >= 0 ? 'text-accent-green' : 'text-accent-red')}>{rMultiples.expectancy >= 0 ? '+' : ''}{rMultiples.expectancy.toFixed(2)}R</span></span>
                    <span className="text-gray-500">{rMultiples.total_trades} trades</span>
                  </div>
                </div>
                <SVGBarChart
                  data={rMultiples.buckets.map((b: any) => ({
                    label: b.label,
                    value: b.count,
                    color: b.color,
                  }))}
                  height={200}
                  formatValue={(v: number) => `${v} trades`}
                />
                <p className="text-[10px] text-muted-foreground mt-2 font-mono">
                  R-Multiple = realized P&L ÷ initial risk (entry × SL% × qty). Positive expectancy requires mean R &gt; 0.
                </p>
              </div>
            </motion.div>
          )}
          {rMultiples?.message && (
            <div className="border border-border rounded-md p-4">
              <SectionLabel>R-Multiple Distribution</SectionLabel>
              <p className="text-sm text-muted-foreground">{rMultiples.message}</p>
            </div>
          )}
        </>
      ) : null}
    </DataSection>
  );
};
