import { type FC, useEffect } from 'react';
import { motion } from 'framer-motion';
import { TrendingUp, Activity } from 'lucide-react';
import { SectionLabel } from '../../components/ui/SectionLabel';
import { MetricCard } from '../../components/trading/MetricCard';
import { InteractiveChart } from '../../components/charts/InteractiveChart';
import { DataSection, ChartSkeleton, MetricGridSkeleton } from '../../components/ui/loading-skeletons';
import { cn } from '../../lib/utils';
import { chartTheme } from '../../lib/design-tokens';
import type { RollingStatsData } from '../../types/analytics';

const WINDOWS = [30, 60, 90] as const;

interface RollingStatisticsTabProps {
  data: RollingStatsData | null;
  loading: boolean;
  error: string | null;
  window: number;
  onWindowChange: (w: number) => void;
  period: string; // kept for future use
  onRetry: () => void;
}

export const RollingStatisticsTab: FC<RollingStatisticsTabProps> = ({
  data,
  loading,
  error,
  window: rollingWindow,
  onWindowChange,
  period: _period,
  onRetry,
}) => {
  // Trigger re-fetch when window changes
  useEffect(() => {
    if (data) onRetry();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rollingWindow]);

  const insufficientData = !loading && !error && data &&
    data.rolling_sharpe.length === 0 &&
    data.rolling_beta.length === 0;

  return (
    <DataSection
      isLoading={loading}
      error={error}
      skeleton={<><MetricGridSkeleton columns={4} /><ChartSkeleton /><ChartSkeleton /><ChartSkeleton /><ChartSkeleton /></>}
      onRetry={onRetry}
    >
      {insufficientData ? (
        <div className="border border-border rounded-md p-12">
          <div className="text-center text-muted-foreground font-mono">
            <Activity className="h-8 w-8 mx-auto mb-3 opacity-50" />
            <p>Minimum {rollingWindow} trading days required for rolling statistics.</p>
            <p className="text-[10px] mt-1">Try selecting a longer period or a shorter rolling window.</p>
          </div>
        </div>
      ) : data ? (
        <>
          {/* Window size toggle */}
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-muted-foreground font-mono">Window:</span>
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                onClick={() => onWindowChange(w)}
                className={cn(
                  'px-3 py-1 text-xs font-mono rounded transition-colors',
                  w === rollingWindow
                    ? 'bg-accent-blue text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-dark-hover',
                )}
              >
                {w}d
              </button>
            ))}
          </div>

          {/* Metric cards */}
          <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }} className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <MetricCard
              label="Probabilistic Sharpe"
              value={`${(data.probabilistic_sharpe * 100).toFixed(1)}%`}
              icon={TrendingUp}
              tooltip="Probability that the Sharpe ratio exceeds 0.5"
              className="border-accent-blue/30"
            />
            <MetricCard
              label="Information Ratio"
              value={data.information_ratio.toFixed(3)}
              format="text"
              tooltip="Risk-adjusted excess return vs benchmark"
            />
            <MetricCard
              label="Treynor Ratio"
              value={data.treynor_ratio.toFixed(3)}
              format="text"
              tooltip="Excess return per unit of systematic risk"
            />
            <MetricCard
              label="Tracking Error"
              value={`${data.tracking_error.toFixed(2)}%`}
              format="text"
              tooltip="Standard deviation of excess returns vs benchmark"
            />
          </motion.div>

          {/* Rolling charts */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Rolling Sharpe Ratio ({rollingWindow}d)</SectionLabel>
              <InteractiveChart
                data={data.rolling_sharpe.map(d => ({ date: d.date, sharpe: d.value }))}
                dataKeys={[{ key: 'sharpe', color: chartTheme.series.portfolio, type: 'line' }]}
                xAxisKey="date"
                height={250}
                showZoom
                tooltipFormatter={(v: number) => [v.toFixed(3), 'Sharpe']}
              />
            </div>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Rolling Beta vs SPY ({rollingWindow}d)</SectionLabel>
              <InteractiveChart
                data={data.rolling_beta.map(d => ({ date: d.date, beta: d.value }))}
                dataKeys={[{ key: 'beta', color: '#eab308', type: 'line' }]}
                xAxisKey="date"
                height={250}
                showZoom
                tooltipFormatter={(v: number) => [v.toFixed(3), 'Beta']}
              />
            </div>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Rolling Alpha ({rollingWindow}d)</SectionLabel>
              <InteractiveChart
                data={data.rolling_alpha.map(d => ({ date: d.date, alpha: d.value }))}
                dataKeys={[{ key: 'alpha', color: chartTheme.series.alpha, type: 'area' }]}
                xAxisKey="date"
                height={250}
                showZoom
                tooltipFormatter={(v: number) => [`${v.toFixed(3)}%`, 'Alpha']}
              />
            </div>
            <div className="border border-border rounded-md p-4">
              <SectionLabel>Rolling Volatility ({rollingWindow}d)</SectionLabel>
              <InteractiveChart
                data={data.rolling_volatility.map(d => ({ date: d.date, volatility: d.value }))}
                dataKeys={[{ key: 'volatility', color: chartTheme.series.drawdown, type: 'area' }]}
                xAxisKey="date"
                height={250}
                showZoom
                tooltipFormatter={(v: number) => [`${v.toFixed(3)}%`, 'Volatility']}
              />
            </div>
          </div>
        </>
      ) : null}
    </DataSection>
  );
};
