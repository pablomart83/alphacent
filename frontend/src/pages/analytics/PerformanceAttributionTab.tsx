import { type FC, useEffect, useMemo } from 'react';
import { Activity } from 'lucide-react';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { TvChart } from '../../components/charts/TvChart';
import { SVGStackedBarChart } from '../../components/charts/SVGStackedBarChart';
import { DataSection, ChartSkeleton, TableSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatPercentage } from '../../lib/utils';
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
            <SVGStackedBarChart
              data={stackedBarData}
              categoryKey="sector"
              series={[
                { key: 'allocation', color: '#3b82f6', label: 'Allocation' },
                { key: 'selection', color: '#22c55e', label: 'Selection' },
                { key: 'interaction', color: '#eab308', label: 'Interaction' },
              ]}
              height={350}
              formatValue={(v) => `${v.toFixed(3)}%`}
            />
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
              <TvChart
                height={300}
                series={[
                  {
                    id: 'allocation',
                    type: 'line',
                    data: data.cumulative_effects.map((d: any) => ({ time: d.date, value: d.allocation })),
                    color: '#3b82f6',
                    lineWidth: 2,
                  },
                  {
                    id: 'selection',
                    type: 'line',
                    data: data.cumulative_effects.map((d: any) => ({ time: d.date, value: d.selection })),
                    color: '#22c55e',
                    lineWidth: 2,
                  },
                  {
                    id: 'interaction',
                    type: 'line',
                    data: data.cumulative_effects.map((d: any) => ({ time: d.date, value: d.interaction })),
                    color: '#eab308',
                    lineWidth: 2,
                  },
                ]}
              />
            </div>
          )}
        </>
      ) : null}
    </DataSection>
  );
};
