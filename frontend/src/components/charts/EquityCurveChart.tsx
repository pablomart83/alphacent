import { type FC, useMemo } from 'react';
import { TvChart, type TvSeriesConfig } from './TvChart';
import { TvPeriodSelector } from './TvPeriodSelector';
import { filterDataByPeriod } from '../../lib/chart-utils';
import { Badge } from '../ui/Badge';
import { chartTheme } from '../../lib/design-tokens';

// ── Types ──────────────────────────────────────────────────────────────────

interface EquityCurveChartProps {
  equityData: Array<{ date: string; equity: number }>;
  spyData?: Array<{ date: string; close: number }>;
  period: string;
  onPeriodChange: (period: string) => void;
  height?: number | string;
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

  return { mainSeries, drawdownSeries, hasSpy };
}

// ── Main Component ─────────────────────────────────────────────────────────

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

export const EquityCurveChart: FC<EquityCurveChartProps> = ({
  equityData,
  spyData,
  period,
  onPeriodChange,
  height = 400,
}) => {
  const { mainSeries, drawdownSeries } = useMemo(
    () => buildSeries(equityData, spyData, period),
    [equityData, spyData, period],
  );

  const numericHeight = typeof height === 'number' ? height : 400;
  const mainHeight = Math.round(numericHeight * 2 / 3);
  const drawdownHeight = Math.round(numericHeight / 3);
  const benchmarkUnavailable = !spyData || spyData.length === 0;
  const fillParent = height === '100%';

  return (
    <div className={fillParent ? 'w-full h-full flex flex-col' : 'w-full'}>
      {/* Header: Period selector + benchmark badge */}
      <div className="flex items-center justify-between mb-1 shrink-0">
        <TvPeriodSelector
          periods={PERIODS}
          activePeriod={period}
          onPeriodChange={onPeriodChange}
        />
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
