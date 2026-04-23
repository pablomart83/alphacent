import { type FC, useMemo } from 'react';
import { TvChart, type TvSeriesConfig } from './TvChart';
import { TvPeriodSelector } from './TvPeriodSelector';
import { filterDataByPeriod } from '../../lib/chart-utils';
import { Badge } from '../ui/Badge';
import { cn } from '../../lib/utils';
import { chartTheme } from '../../lib/design-tokens';

// ── Types ──────────────────────────────────────────────────────────────────

interface EquityCurveChartProps {
  equityData: Array<{ date: string; equity: number }>;
  /** Realized-only equity curve (same dates, realized P&L cumulative) */
  realizedData?: Array<{ date: string; realized: number }>;
  spyData?: Array<{ date: string; close: number }>;
  period: string;
  onPeriodChange: (period: string) => void;
  interval?: string;
  onIntervalChange?: (interval: string) => void;
  height?: number | string;
  /** Optional closed trades for trade markers on the equity curve */
  trades?: Array<{ date: string; pnl: number; symbol?: string }>;
}

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Normalize a value series to base 100 starting from the first element.
 */
function normalizeToBase100(
  data: Array<{ date: string; value: number }>,
): Array<{ date: string; value: number }> {
  if (data.length === 0) return [];
  const base = data[0].value;
  if (base === 0) return data;
  return data.map((d) => ({ date: d.date, value: (d.value / base) * 100 }));
}

/**
 * Compute drawdown from peak for a value series.
 * Returns percentage drawdown (0 to negative values).
 */
function computeDrawdown(
  data: Array<{ date: string; value: number }>,
): Array<{ date: string; drawdown: number }> {
  if (data.length === 0) return [];
  let peak = -Infinity;
  return data.map((d) => {
    if (d.value > peak) peak = d.value;
    const dd = peak > 0 ? ((d.value - peak) / peak) * 100 : 0;
    return { date: d.date, drawdown: dd };
  });
}

// ── Series builders ────────────────────────────────────────────────────────

function buildSeries(
  equityData: Array<{ date: string; equity: number }>,
  spyData: Array<{ date: string; close: number }> | undefined,
  period: string,
  trades?: Array<{ date: string; pnl: number; symbol?: string }>,
  realizedData?: Array<{ date: string; realized: number }>,
) {
  // Filter equity data by period
  const filteredEquity = filterDataByPeriod(
    equityData.map((d) => ({ ...d })),
    'date',
    period,
  );

  // Normalize portfolio
  const normPortfolio = normalizeToBase100(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );

  const hasSpy = !!spyData && spyData.length > 0;

  // Build SPY-aligned normalized data
  let normSpyMap = new Map<string, number>();
  if (hasSpy) {
    const spyMap = new Map<string, number>();
    for (const s of spyData!) spyMap.set(s.date, s.close);

    const alignedSpy: Array<{ date: string; value: number }> = [];
    for (const d of filteredEquity) {
      const spyVal = spyMap.get(d.date);
      if (spyVal !== undefined) alignedSpy.push({ date: d.date, value: spyVal });
    }
    const normSpy = normalizeToBase100(alignedSpy);
    for (const s of normSpy) normSpyMap.set(s.date, s.value);
  }

  // ── Main chart series ──
  const mainSeries: TvSeriesConfig[] = [];

  // Alpha baseline series (green above SPY, red below)
  if (hasSpy) {
    // Compute alpha = portfolio - spy for each date, centered on 0
    const alphaData = normPortfolio
      .filter((d) => normSpyMap.has(d.date))
      .map((d) => ({
        time: d.date,
        value: d.value - (normSpyMap.get(d.date) ?? 0),
      }));

    mainSeries.push({
      id: 'alpha',
      type: 'baseline',
      data: alphaData,
      baseValue: 0,
      topFillColor1: 'rgba(34, 197, 94, 0.18)',
      topFillColor2: 'rgba(34, 197, 94, 0.02)',
      bottomFillColor1: 'rgba(239, 68, 68, 0.02)',
      bottomFillColor2: 'rgba(239, 68, 68, 0.18)',
      topLineColor: 'transparent',
      bottomLineColor: 'transparent',
      lineWidth: 0,
      priceScaleId: 'alpha',
    });

    // SPY benchmark — gray dashed line
    mainSeries.push({
      id: 'spy',
      type: 'line',
      data: normPortfolio
        .filter((d) => normSpyMap.has(d.date))
        .map((d) => ({ time: d.date, value: normSpyMap.get(d.date)! })),
      color: chartTheme.series.benchmark,
      lineWidth: 1,
      dashed: true,
    });
  }

  // Portfolio — blue area series (on top)
  mainSeries.push({
    id: 'portfolio',
    type: 'area',
    data: normPortfolio.map((d) => ({ time: d.date, value: d.value })),
    lineColor: chartTheme.series.portfolio,
    topColor: 'rgba(59, 130, 246, 0.18)',
    bottomColor: 'transparent',
    lineWidth: 2,
  });

  // Realized-only line — dashed green, normalized to same base as portfolio
  if (realizedData && realizedData.length > 0) {
    const filteredRealized = filterDataByPeriod(
      realizedData.map(d => ({ date: d.date, value: d.realized })),
      'date',
      period,
    );
    const normRealized = normalizeToBase100(filteredRealized);
    if (normRealized.length > 0) {
      mainSeries.push({
        id: 'realized',
        type: 'line',
        data: normRealized.map(d => ({ time: d.date, value: d.value })),
        color: '#22c55e',
        lineWidth: 1,
        dashed: true,
      });
    }
  }

  // Trade markers — green dots for wins, red dots for losses, sized by |P&L|
  // Rendered as a scatter-style line series with zero width (just markers)
  const tradeMarkers: Array<{ time: string; value: number; color: string; size: number }> = [];
  if (trades && trades.length > 0 && normPortfolio.length > 0) {
    const equityMap = new Map(normPortfolio.map(d => [d.date, d.value]));
    const filteredTrades = filterDataByPeriod(
      trades.map(t => ({ ...t })),
      'date',
      period,
    );
    for (const trade of filteredTrades) {
      const date = trade.date?.slice(0, 10);
      if (!date) continue;
      // Find nearest equity value for this date
      const equityVal = equityMap.get(date) ?? [...equityMap.entries()]
        .filter(([d]) => d <= date)
        .sort(([a], [b]) => b.localeCompare(a))[0]?.[1];
      if (equityVal === undefined) continue;
      const absP = Math.abs(trade.pnl);
      // Size: 1-4 based on P&L magnitude (capped at $500 for max size)
      const size = Math.min(4, Math.max(1, Math.round(absP / 125)));
      tradeMarkers.push({
        time: date,
        value: equityVal,
        color: trade.pnl >= 0 ? '#22c55e' : '#ef4444',
        size,
      });
    }
  }

  if (tradeMarkers.length > 0) {
    mainSeries.push({
      id: 'trade_markers',
      type: 'line',
      data: tradeMarkers.map(m => ({ time: m.time, value: m.value, color: m.color })),
      color: 'transparent',
      lineWidth: 0,
    });
    // Store markers for post-render attachment via __markers
    (mainSeries[mainSeries.length - 1] as any).__tradeMarkers = tradeMarkers.map(m => ({
      time: m.time,
      position: 'inBar' as const,
      color: m.color,
      shape: 'circle' as const,
      size: m.size,
      text: '',
    }));
  }

  // ── Drawdown sub-chart series ──
  const drawdownRaw = computeDrawdown(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );

  const drawdownSeries: TvSeriesConfig[] = [
    {
      id: 'drawdown',
      type: 'area',
      data: drawdownRaw.map((d) => ({ time: d.date, value: d.drawdown })),
      lineColor: chartTheme.series.drawdown,
      topColor: 'rgba(239, 68, 68, 0.4)',
      bottomColor: 'rgba(239, 68, 68, 0.05)',
      lineWidth: 1,
    },
  ];

  return { mainSeries, drawdownSeries, hasSpy, hasRealized: !!(realizedData && realizedData.length > 0) };
}

// ── Main Component ─────────────────────────────────────────────────────────

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

export const EquityCurveChart: FC<EquityCurveChartProps> = ({
  equityData,
  realizedData,
  spyData,
  period,
  onPeriodChange,
  interval = '1d',
  onIntervalChange,
  height = 400,
  trades,
}) => {
  const { mainSeries, drawdownSeries, hasRealized } = useMemo(
    () => buildSeries(equityData, spyData, period, trades, realizedData),
    [equityData, realizedData, spyData, period, trades],
  );

  const numericHeight = typeof height === 'number' ? height : 400;
  const mainHeight = Math.round(numericHeight * 2 / 3);
  const drawdownHeight = Math.round(numericHeight / 3);
  const benchmarkUnavailable = !spyData || spyData.length === 0;
  const fillParent = height === '100%';

  return (
    <div className={fillParent ? 'w-full h-full flex flex-col' : 'w-full'}>
      {/* Header: Period selector + interval selector + legend + benchmark badge */}
      <div className="flex items-center justify-between mb-1 shrink-0">
        <div className="flex items-center gap-3">
          <TvPeriodSelector
            periods={PERIODS}
            activePeriod={period}
            onPeriodChange={onPeriodChange}
          />
          {/* Interval selector — only shown when handler is provided */}
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
                      interval === iv
                        ? 'bg-gray-700 text-gray-100'
                        : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/50'
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
            {!benchmarkUnavailable && (
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
        {benchmarkUnavailable && (
          <Badge variant="warning">Benchmark unavailable</Badge>
        )}
      </div>

      {/* Main equity curve chart */}
      <div className={fillParent ? 'flex-1 min-h-0' : ''}>
        <TvChart
          series={mainSeries}
          height={fillParent ? mainHeight : mainHeight}
          showTimeScale={false}
          autoResize
        />
      </div>

      {/* Drawdown sub-chart */}
      <div className="shrink-0">
        <TvChart
          series={drawdownSeries}
          height={fillParent ? 80 : drawdownHeight}
          showTimeScale
          autoResize
        />
      </div>
    </div>
  );
};

export { normalizeToBase100, computeDrawdown };
export type { EquityCurveChartProps };
