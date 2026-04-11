import { type FC, useMemo } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle } from 'lucide-react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell,
} from 'recharts';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '../../components/ui/Card';
import { MetricCard } from '../../components/trading/MetricCard';
import { InteractiveChart } from '../../components/charts/InteractiveChart';
import { DataSection, ChartSkeleton, MetricGridSkeleton, TableSkeleton, HeatmapSkeleton } from '../../components/ui/loading-skeletons';
import { cn, formatCurrency } from '../../lib/utils';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
  colors,
} from '../../lib/design-tokens';
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
        <Card>
          <CardContent className="py-12">
            <div className="text-center text-muted-foreground font-mono">
              <AlertTriangle className="h-8 w-8 mx-auto mb-3 opacity-50" />
              <p>Minimum 10 closed trades required for meaningful execution quality analysis.</p>
              <p className="text-sm mt-1">Try selecting a longer period.</p>
            </div>
          </CardContent>
        </Card>
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
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Slippage by Symbol</CardTitle>
                <CardDescription className="font-mono text-xs">Red &gt; 0.5%, Yellow 0.1-0.5%</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={Math.max(250, data.slippage_by_symbol.length * 28)}>
                  <BarChart data={data.slippage_by_symbol} layout="vertical">
                    <CartesianGrid {...chartGridProps} />
                    <XAxis type="number" {...chartAxisProps} tickFormatter={(v: number) => `${v.toFixed(2)}%`} />
                    <YAxis type="category" dataKey="symbol" {...chartAxisProps} width={80} />
                    <Tooltip
                      contentStyle={{ ...chartTooltipStyle, fontFamily: chartTheme.fontFamily, fontSize: 11 }}
                      formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(3)}%`, 'Avg Slippage']}
                      labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
                    />
                    <Bar dataKey="avg_slippage_pct" radius={[0, 4, 4, 0]}>
                      {data.slippage_by_symbol.map((entry, idx) => (
                        <Cell key={idx} fill={slippageColor(entry.avg_slippage_pct)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </motion.div>

          {/* Slippage by Time of Day heatmap */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.1 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Slippage by Time of Day</CardTitle>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>
          </motion.div>

          {/* Slippage by Order Size */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.15 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Slippage by Order Size</CardTitle>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={250}>
                  <BarChart data={data.slippage_by_size}>
                    <CartesianGrid {...chartGridProps} />
                    <XAxis dataKey="bucket" {...chartAxisProps} />
                    <YAxis {...chartAxisProps} tickFormatter={(v: number) => `${v.toFixed(2)}%`} />
                    <Tooltip
                      contentStyle={{ ...chartTooltipStyle, fontFamily: chartTheme.fontFamily, fontSize: 11 }}
                      formatter={((value: number | undefined, name: string) => {
                        if (name === 'avg_slippage') return [`${(value ?? 0).toFixed(3)}%`, 'Avg Slippage'];
                        return [String(value ?? 0), name];
                      }) as never}
                      labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
                    />
                    <Bar dataKey="avg_slippage" fill={colors.blue} radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </motion.div>

          {/* Implementation Shortfall Table */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.2 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Implementation Shortfall</CardTitle>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>
          </motion.div>

          {/* Fill Rate Analysis */}
          {data.fill_rate_buckets.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.25 }}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Fill Rate Analysis</CardTitle>
                </CardHeader>
                <CardContent>
                  <ResponsiveContainer width="100%" height={220}>
                    <BarChart data={data.fill_rate_buckets.map(b => ({
                      label: b.within_seconds < 60 ? `${b.within_seconds}s` : `${Math.round(b.within_seconds / 60)}min`,
                      percentage: b.percentage,
                    }))}>
                      <CartesianGrid {...chartGridProps} />
                      <XAxis dataKey="label" {...chartAxisProps} />
                      <YAxis {...chartAxisProps} tickFormatter={(v: number) => `${v}%`} />
                      <Tooltip
                        contentStyle={{ ...chartTooltipStyle, fontFamily: chartTheme.fontFamily, fontSize: 11 }}
                        formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(1)}%`, 'Fill Rate']}
                        labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
                      />
                      <Bar dataKey="percentage" fill={colors.blue} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Execution Quality Trend */}
          {data.execution_quality_trend.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.3 }}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">Execution Quality Trend</CardTitle>
                </CardHeader>
                <CardContent>
                  <InteractiveChart
                    data={data.execution_quality_trend}
                    dataKeys={[{ key: 'avg_slippage', color: chartTheme.series.drawdown, type: 'line' }]}
                    xAxisKey="date"
                    height={250}
                    showZoom
                    tooltipFormatter={(v: number) => [`${v.toFixed(4)}%`, 'Avg Slippage']}
                  />
                </CardContent>
              </Card>
            </motion.div>
          )}

          {/* Per Asset Class breakdown */}
          {data.per_asset_class.length > 0 && (
            <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.3, delay: 0.35 }}>
              <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
                {data.per_asset_class.map(ac => (
                  <Card key={ac.asset_class}>
                    <CardContent className="pt-4 pb-3">
                      <p className="text-xs text-muted-foreground mb-1 font-mono">{ac.asset_class}</p>
                      <p className="text-lg font-bold font-mono">{ac.avg_slippage.toFixed(3)}%</p>
                      <p className="text-xs text-muted-foreground font-mono">{ac.avg_shortfall_bps.toFixed(1)} bps · {ac.trade_count} trades</p>
                    </CardContent>
                  </Card>
                ))}
              </div>
            </motion.div>
          )}

          {/* Worst Executions Table */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: 0.4 }}>
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Worst Executions (Top 10)</CardTitle>
              </CardHeader>
              <CardContent>
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
              </CardContent>
            </Card>
          </motion.div>
        </>
      ) : null}
    </DataSection>
  );
};
