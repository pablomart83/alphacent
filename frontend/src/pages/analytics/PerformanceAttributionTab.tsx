import { type FC, useEffect, useMemo } from 'react';
import { Activity } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend,
} from 'recharts';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { InteractiveChart } from '../../components/charts/InteractiveChart';
import { DataSection, ChartSkeleton, TableSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatPercentage } from '../../lib/utils';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
} from '../../lib/design-tokens';
import type { AttributionData } from '../../types/analytics';

interface PerformanceAttributionTabProps {
  data: AttributionData | null;
  loading: boolean;
  error: string | null;
  groupBy: 'sector' | 'asset_class';
  onGroupByChange: (g: 'sector' | 'asset_class') => void;
  period: string; // kept for future use
  onRetry: () => void;
}

export const PerformanceAttributionTab: FC<PerformanceAttributionTabProps> = ({
  data,
  loading,
  error,
  groupBy,
  onGroupByChange,
  period: _period,
  onRetry,
}) => {
  // Re-fetch when groupBy changes
  useEffect(() => {
    if (data) onRetry();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [groupBy]);

  const insufficientData = !loading && !error && data &&
    data.sectors.length === 0;

  const stackedBarData = useMemo(() => {
    if (!data) return [];
    return data.sectors.map(s => ({
      sector: s.sector,
      allocation: s.allocation_effect,
      selection: s.selection_effect,
      interaction: s.interaction_effect,
    }));
  }, [data]);

  return (
    <DataSection
      isLoading={loading}
      error={error}
      skeleton={<><ChartSkeleton /><TableSkeleton rows={6} columns={9} /><ChartSkeleton /></>}
      onRetry={onRetry}
    >
      {insufficientData ? (
        <div className="border border-border rounded-md py-12">
          <div className="text-center text-muted-foreground font-mono">
            <Activity className="h-8 w-8 mx-auto mb-3 opacity-50" />
            <p>Minimum number of closed trades required for meaningful attribution analysis.</p>
            <p className="text-[10px] mt-1">Try selecting a longer period.</p>
          </div>
        </div>
      ) : data ? (
        <>
          {/* Group by toggle */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-mono">Group by:</span>
            {(['sector', 'asset_class'] as const).map((g) => (
              <button
                key={g}
                type="button"
                onClick={() => onGroupByChange(g)}
                className={cn(
                  'px-3 py-1 text-xs font-mono rounded transition-colors',
                  g === groupBy
                    ? 'bg-accent-blue text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover',
                )}
              >
                {g === 'sector' ? 'Sector' : 'Asset Class'}
              </button>
            ))}
          </div>

          {/* Stacked bar chart */}
          <div className="border border-border rounded-md p-4">
            <SectionLabel>Attribution Effects by {groupBy === 'sector' ? 'Sector' : 'Asset Class'}</SectionLabel>
            <ResponsiveContainer width="100%" height={350}>
              <BarChart data={stackedBarData}>
                <CartesianGrid {...chartGridProps} />
                <XAxis dataKey="sector" {...chartAxisProps} />
                <YAxis {...chartAxisProps} tickFormatter={(v: number) => `${v.toFixed(1)}%`} />
                <Tooltip
                  contentStyle={{ ...chartTooltipStyle, fontFamily: chartTheme.fontFamily, fontSize: 11 }}
                  formatter={((value: number | undefined, name: string) => [`${(value ?? 0).toFixed(3)}%`, name.charAt(0).toUpperCase() + name.slice(1)]) as never}
                  labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
                />
                <Legend />
                <Bar dataKey="allocation" stackId="a" fill="#3b82f6" name="Allocation" />
                <Bar dataKey="selection" stackId="a" fill="#22c55e" name="Selection" />
                <Bar dataKey="interaction" stackId="a" fill="#eab308" name="Interaction" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Attribution summary table */}
          <div className="border border-border rounded-md p-4">
            <SectionLabel>Attribution Summary</SectionLabel>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-border">
                    {['Sector', 'Port. Wt', 'Bench. Wt', 'Port. Ret', 'Bench. Ret', 'Allocation', 'Selection', 'Interaction', 'Total'].map(h => (
                      <th key={h} className="px-3 py-2 text-left text-xs font-mono text-muted-foreground">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {data.sectors.map((s, i) => (
                    <tr key={s.sector} className={cn('border-b border-border/50', i % 2 === 0 && 'bg-muted/30')}>
                      <td className="px-3 py-2 font-mono font-semibold text-sm">{s.sector}</td>
                      <td className="px-3 py-2 font-mono text-sm">{formatPercentage(s.portfolio_weight)}</td>
                      <td className="px-3 py-2 font-mono text-sm">{formatPercentage(s.benchmark_weight)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm', s.portfolio_return >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.portfolio_return)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm', s.benchmark_return >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.benchmark_return)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm', s.allocation_effect >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.allocation_effect, 3)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm', s.selection_effect >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.selection_effect, 3)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm', s.interaction_effect >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.interaction_effect, 3)}</td>
                      <td className={cn('px-3 py-2 font-mono text-sm font-semibold', s.total_contribution >= 0 ? 'text-accent-green' : 'text-accent-red')}>{formatPercentage(s.total_contribution, 3)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Cumulative effects time-series */}
          {data.cumulative_effects.length > 0 && (
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Cumulative Attribution Effects</SectionLabel>
              <InteractiveChart
                data={data.cumulative_effects}
                dataKeys={[
                  { key: 'allocation', color: '#3b82f6', type: 'line' },
                  { key: 'selection', color: '#22c55e', type: 'line' },
                  { key: 'interaction', color: '#eab308', type: 'line' },
                ]}
                xAxisKey="date"
                height={300}
                showZoom
                tooltipFormatter={(v: number, name: string) => [`${v.toFixed(3)}%`, name.charAt(0).toUpperCase() + name.slice(1)]}
              />
            </div>
          )}
        </>
      ) : null}
    </DataSection>
  );
};
