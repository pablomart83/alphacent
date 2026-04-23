import { type FC } from 'react';
import { TvChart, type TvSeriesConfig } from './TvChart';
import { TvPeriodSelector } from './TvPeriodSelector';
import { Badge } from '../ui/Badge';
import { cn } from '../../lib/utils';

// ── Types ──────────────────────────────────────────────────────────────────

export interface EquityCurveChartProps {
  /** Pre-built main chart series (portfolio, SPY, alpha, realized, markers) */
  mainSeries: TvSeriesConfig[];
  /** Pre-built drawdown series */
  drawdownSeries: TvSeriesConfig[];
  /** Whether SPY data is available (controls legend + badge) */
  hasSpy?: boolean;
  /** Whether realized line is present (controls legend) */
  hasRealized?: boolean;
  period: string;
  onPeriodChange: (period: string) => void;
  interval?: string;
  onIntervalChange?: (interval: string) => void;
  height?: number;
}

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

export const EquityCurveChart: FC<EquityCurveChartProps> = ({
  mainSeries,
  drawdownSeries,
  hasSpy = false,
  hasRealized = false,
  period,
  onPeriodChange,
  interval = '1d',
  onIntervalChange,
  height = 400,
}) => {
  const mainHeight = Math.round(height * 2 / 3);
  const drawdownHeight = Math.round(height / 3);

  return (
    <div className="w-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-1 shrink-0">
        <div className="flex items-center gap-3">
          <TvPeriodSelector periods={PERIODS} activePeriod={period} onPeriodChange={onPeriodChange} />
          {onIntervalChange && (
            <>
              <span className="text-gray-700 select-none">|</span>
              <div className="flex items-center gap-0.5">
                {(['1d', '4h', '1h'] as const).map((iv) => (
                  <button
                    key={iv}
                    onClick={() => onIntervalChange(iv)}
                    className={cn(
                      'px-2 py-0.5 text-xs font-mono font-medium rounded transition-colors',
                      interval === iv ? 'bg-gray-700 text-gray-100' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50',
                    )}
                  >
                    {iv.toUpperCase()}
                  </button>
                ))}
              </div>
            </>
          )}
          <div className="flex items-center gap-3 text-xs font-mono">
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-[#3b82f6] rounded" />
              <span className="text-gray-400">Total (R+U)</span>
            </span>
            {hasRealized && (
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 rounded" style={{ borderTop: '1px dashed #22c55e' }} />
                <span className="text-gray-400">Realised</span>
              </span>
            )}
            {hasSpy && (
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-0.5 bg-gray-500 rounded" style={{ borderTop: '1px dashed #6b7280' }} />
                <span className="text-gray-400">SPY</span>
              </span>
            )}
            <span className="flex items-center gap-1.5">
              <span className="w-3 h-0.5 bg-[#ef4444] rounded" />
              <span className="text-gray-400">Drawdown</span>
            </span>
          </div>
        </div>
        {!hasSpy && <Badge variant="warning">Benchmark unavailable</Badge>}
      </div>

      {/* Main chart */}
      <TvChart series={mainSeries} height={mainHeight} showTimeScale={false} autoResize />

      {/* Drawdown sub-chart */}
      <TvChart series={drawdownSeries} height={drawdownHeight} showTimeScale autoResize />
    </div>
  );
};

// Re-export helpers so callers don't need to import from two places
export { buildEquityCurveSeries, normalizeToBase100, computeDrawdown } from '../../lib/chart-utils';
