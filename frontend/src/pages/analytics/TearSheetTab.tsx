import { type FC } from 'react';
import { motion } from 'framer-motion';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell,
} from 'recharts';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { UnderwaterPlot } from '../../components/charts/UnderwaterPlot';
import { ReturnDistribution } from '../../components/charts/ReturnDistribution';
import { MonthlyReturnsHeatmap } from '../../components/charts/MonthlyReturnsHeatmap';
import { DataSection, ChartSkeleton, TableSkeleton, HeatmapSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatPercentage } from '../../lib/utils';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
  colors,
} from '../../lib/design-tokens';
import type { TearSheetData } from '../../types/analytics';

interface TearSheetTabProps {
  data: TearSheetData | null;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

export const TearSheetTab: FC<TearSheetTabProps> = ({
  data,
  loading,
  error,
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
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={data.annual_returns}>
                    <CartesianGrid {...chartGridProps} />
                    <XAxis dataKey="year" {...chartAxisProps} />
                    <YAxis {...chartAxisProps} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                    <Tooltip
                      contentStyle={{ ...chartTooltipStyle, fontFamily: chartTheme.fontFamily, fontSize: 11 }}
                      formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(2)}%`, 'Return']}
                      labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
                    />
                    <Bar dataKey="return_pct" radius={[4, 4, 0, 0]}>
                      {data.annual_returns.map((entry, idx) => (
                        <Cell key={idx} fill={entry.return_pct >= 0 ? colors.green : colors.red} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
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
        </>
      ) : null}
    </DataSection>
  );
};
