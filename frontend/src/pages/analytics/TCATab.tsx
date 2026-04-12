import { type FC, useMemo } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { MetricCard } from '../../components/trading/MetricCard';
import { TvChart } from '../../components/charts/TvChart';
import { SVGBarChart } from '../../components/charts/SVGBarChart';
import { DataSection, ChartSkeleton, MetricGridSkeleton, TableSkeleton, HeatmapSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatCurrency } from '../../lib/utils';
import { colors } from '../../lib/design-tokens';
import {
  Tooltip as UITooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../../components/ui/tooltip';
import type { TCAData } from '../../types/analytics';

interface TCATabProps {
  data: TCAData | null;
  loading: boolean;
  error: string | null;
  period: string; // kept for future use
  onRetry: () => void;
}

function slippageColor(pct: number): string {
  if (pct > 0.5) return colors.red;
  if (pct > 0.1) return colors.yellow;
  return colors.green;
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];

export const TCATab: FC<TCATabProps> = ({
  data,
  loading,
  error,
  period: _period,
  onRetry,
}) => {
  const insufficientData = !loading && !error && data &&
    data.slippage_by_symbol.length === 0 &&
    data.implementation_shortfall.length === 0;

  // Build slippage heatmap grid
  const heatmapGrid = useMemo(() => {
    if (!data?.slippage_by_hour) return new Map<string, number>();
    const grid = new Map<string, number>();
    for (const entry of data.slippage_by_hour) {
      grid.set(`${entry.day}-${entry.hour}`, entry.avg_slippage);
    }
    return grid;
  }, [data]);

  return (
    <DataSection
      isLoading={loading}
      error={error}
      skeleton={
        <>
          <MetricGridSkeleton columns={2} />
          <ChartSkeleton />
          <HeatmapSkeleton rows={7} columns={24} />
          <ChartSkeleton />
          <TableSkeleton rows={8} columns={7} />
          <ChartSkeleton />
          <MetricGridSkeleton columns={4} />
          <TableSkeleton rows={10} columns={7} />
        </>
      }
      onRetry={onRetry}
    >
      {insufficientData ? (
        <div className="border border-border rounded-md py-12">
          <div className="text-center text-muted-foreground font-mono">
            <AlertTriangle className="h-8 w-8 mx-auto mb-3 opacity-50" />
            <p>Minimum 10 closed trades required for meaningful execution quality analysis.</p>
            <p className="text-[10px] mt-1">Try selecting a longer period.</p>
          </div>
        </div>
      ) : data ? (
        <>
          {/* Headline metrics */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }} className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <MetricCard
              label="Cost as % of Alpha"
              value={`${data.cost_as_pct_of_alpha.toFixed(2)}%`}
              format="text"
              icon={AlertTriangle}
              tooltip="Total execution costs as a percentage of gross portfolio returns"
              className="border-accent-blue/30 md:col-span-1"
            />
            <MetricCard
              label="Total Implementation Shortfall"
              value={formatCurrency(data.total_shortfall_dollars)}
              format="text"
              tooltip={`${data.total_shortfall_bps.toFixed(1)} bps across all closed trades`}
            />
          </motion.div>

          {/* Slippage by Symbol */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.05 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Slippage by Symbol</SectionLabel>
              <p className="text-[10px] font-mono text-muted-foreground mb-2">Red &gt; 0.5%, Yellow 0.1-0.5%</p>
              <SVGBarChart
                data={data.slippage_by_symbol.map((entry) => ({
                  label: entry.symbol,
                  value: entry.avg_slippage_pct,
                  color: slippageColor(entry.avg_slippage_pct),
                }))}
                height={Math.max(250, data.slippage_by_symbol.length * 28)}
                horizontal
                formatValue={(v: number) => `${v.toFixed(3)}%`}
              />
            </div>
          </motion.div>

          {/* Slippage by Time of Day heatmap */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Slippage by Time of Day</SectionLabel>
              <TooltipProvider>
                <div className="overflow-x-auto">
                  <table className="border-collapse">
                    <thead>
                      <tr>
                        <th className="px-1 py-1 text-xs font-mono text-muted-foreground">Day</th>
                        {Array.from({ length: 24 }, (_, h) => (
                          <th key={h} className="px-0.5 py-1 text-[10px] font-mono text-muted-foreground text-center">{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {DAYS.map(day => (
                        <tr key={day}>
                          <td className="px-1 py-0.5 text-xs font-mono text-muted-foreground">{day}</td>
                          {Array.from({ length: 24 }, (_, h) => {
                            const val = heatmapGrid.get(`${day}-${h}`);
                            const hasVal = val !== undefined;
                            return (
                              <td key={h} className="px-0.5 py-0.5">
                                <UITooltip>
                                  <TooltipTrigger asChild>
                                    <div className={cn(
                                      'w-6 h-6 rounded-sm',
                                      hasVal
                                        ? val! > 0.5 ? 'bg-red-500/70' : val! > 0.1 ? 'bg-yellow-500/50' : 'bg-green-500/30'
                                        : 'bg-gray-800/30',
                                    )} />
                                  </TooltipTrigger>
                                  {hasVal && (
                                    <TooltipContent>
                                      <span className="font-mono text-xs">{day} {h}:00 — {val!.toFixed(3)}%</span>
                                    </TooltipContent>
                                  )}
                                </UITooltip>
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </TooltipProvider>
            </div>
          </motion.div>

          {/* Slippage by Order Size */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.15 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Slippage by Order Size</SectionLabel>
              <SVGBarChart
                data={data.slippage_by_size.map((entry) => ({
                  label: entry.bucket,
                  value: entry.avg_slippage,
                }))}
                height={250}
                color={colors.blue}
                formatValue={(v: number) => `${v.toFixed(3)}%`}
              />
            </div>
          </motion.div>

          {/* Implementation Shortfall Table */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Implementation Shortfall</SectionLabel>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Symbol', 'Expected', 'Fill', 'Mkt Close', 'Shortfall ($)', 'Shortfall (bps)', 'Date'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-xs font-mono text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.implementation_shortfall.slice(0, 20).map((row, i) => (
                      <tr key={i} className={cn('border-b border-border/50', i % 2 === 0 && 'bg-muted/30')}>
                        <td className="px-3 py-2 font-mono font-semibold text-sm">{row.symbol}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.expected_price)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.fill_price)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.market_close_price)}</td>
                        <td className={cn('px-3 py-2 font-mono text-sm', row.shortfall_dollars > 0 ? 'text-accent-red' : 'text-accent-green')}>{formatCurrency(row.shortfall_dollars)}</td>
                        <td className={cn('px-3 py-2 font-mono text-sm', row.shortfall_bps > 0 ? 'text-accent-red' : 'text-accent-green')}>{row.shortfall_bps.toFixed(1)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{row.trade_date}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>

          {/* Fill Rate Analysis */}
          {data.fill_rate_buckets.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.25 }}>
              <div className="border border-border rounded-md p-4">
                <SectionLabel>Fill Rate Analysis</SectionLabel>
                <SVGBarChart
                  data={data.fill_rate_buckets.map(b => ({
                    label: b.within_seconds < 60 ? `${b.within_seconds}s` : `${Math.round(b.within_seconds / 60)}min`,
                    value: b.percentage,
                  }))}
                  height={220}
                  color={colors.blue}
                  formatValue={(v: number) => `${v.toFixed(1)}%`}
                />
              </div>
            </motion.div>
          )}

          {/* Execution Quality Trend */}
          {data.execution_quality_trend.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}>
              <div className="border border-border rounded-md p-4">
                <SectionLabel>Execution Quality Trend</SectionLabel>
                <TvChart
                  height={250}
                  series={[{
                    id: 'avgSlippage',
                    type: 'line',
                    data: data.execution_quality_trend.map((d: any) => ({
                      time: d.date,
                      value: d.avg_slippage,
                    })),
                    color: '#ef4444',
                    lineWidth: 2,
                  }]}
                />
              </div>
            </motion.div>
          )}

          {/* Per Asset Class breakdown */}
          {data.per_asset_class.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.35 }}>
              <SectionLabel>Per Asset Class</SectionLabel>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {data.per_asset_class.map(ac => (
                  <div key={ac.asset_class} className="border border-border rounded-md px-3 pt-3 pb-2">
                    <p className="text-[10px] text-muted-foreground mb-1 font-mono">{ac.asset_class}</p>
                    <p className="text-[13px] font-bold font-mono">{ac.avg_slippage.toFixed(3)}%</p>
                    <p className="text-[10px] text-muted-foreground font-mono">{ac.avg_shortfall_bps.toFixed(1)} bps · {ac.trade_count} trades</p>
                  </div>
                ))}
              </div>
            </motion.div>
          )}

          {/* Worst Executions Table */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4 }}>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Worst Executions (Top 10)</SectionLabel>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      {['Symbol', 'Expected', 'Fill', 'Slippage', 'Timestamp', 'Size ($)', 'Asset Class'].map(h => (
                        <th key={h} className="px-3 py-2 text-left text-xs font-mono text-muted-foreground">{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {data.worst_executions.slice(0, 10).map((row, i) => (
                      <tr key={i} className={cn('border-b border-border/50', i % 2 === 0 && 'bg-muted/30')}>
                        <td className="px-3 py-2 font-mono font-semibold text-sm">{row.symbol}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.expected_price)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.fill_price)}</td>
                        <td className="px-3 py-2 font-mono text-sm text-accent-red">{row.slippage_pct.toFixed(3)}%</td>
                        <td className="px-3 py-2 font-mono text-sm">{row.timestamp}</td>
                        <td className="px-3 py-2 font-mono text-sm">{formatCurrency(row.order_size_dollars)}</td>
                        <td className="px-3 py-2 font-mono text-sm">{row.asset_class}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </motion.div>
        </>
      ) : null}
    </DataSection>
  );
};
