import { type FC } from 'react';
import { TvChart, type TvSeriesConfig } from './TvChart';
import { TvPeriodSelector } from './TvPeriodSelector';
import { cn } from '../../lib/utils';

export interface EquityCurveChartProps {
  mainSeries: TvSeriesConfig[];
  drawdownSeries: TvSeriesConfig[];
  hasSpy?: boolean;
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
  const mainHeight = Math.round(height * 0.72);
  const ddHeight = Math.round(height * 0.28);

  return (
    <div className="w-full flex flex-col gap-0">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-0.5 mb-0.5">
        <div className="flex items-center gap-2">
          <TvPeriodSelector periods={PERIODS} activePeriod={period} onPeriodChange={onPeriodChange} />
          {onIntervalChange && (
            <div className="flex items-center gap-px border border-gray-800 rounded overflow-hidden">
              {(['1d', '4h', '1h'] as const).map((iv) => (
                <button
                  key={iv}
                  onClick={() => onIntervalChange(iv)}
                  className={cn(
                    'px-2 py-0.5 text-[10px] font-mono font-medium transition-colors',
                    interval === iv
                      ? 'bg-gray-700 text-gray-100'
                      : 'text-gray-600 hover:text-gray-300 hover:bg-gray-800/60',
                  )}
                >
                  {iv.toUpperCase()}
                </button>
              ))}
            </div>
          )}
        </div>
        {/* Legend */}
        <div className="flex items-center gap-3 text-[10px] font-mono text-gray-500">
          <span className="flex items-center gap-1">
            <span className="w-4 h-[2px] bg-[#3b82f6] inline-block rounded" />
            Total
          </span>
          {hasRealized && (
            <span className="flex items-center gap-1">
              <span className="w-4 inline-block" style={{ borderTop: '1.5px dashed #22c55e' }} />
              Realised
            </span>
          )}
          {hasSpy && (
            <span className="flex items-center gap-1">
              <span className="w-4 inline-block" style={{ borderTop: '1.5px dashed #6b7280' }} />
              SPY
            </span>
          )}
          <span className="flex items-center gap-1">
            <span className="w-4 h-[2px] bg-[#ef4444] inline-block rounded opacity-70" />
            DD
          </span>
        </div>
      </div>

      {/* Main equity chart */}
      <TvChart
        series={mainSeries}
        height={mainHeight}
        showTimeScale={false}
        autoResize
      />

      {/* Drawdown — compact strip below */}
      <TvChart
        series={drawdownSeries}
        height={ddHeight}
        showTimeScale
        autoResize
      />
    </div>
  );
};

export { buildEquityCurveSeries, normalizeToBase100, computeDrawdown } from '../../lib/chart-utils';
