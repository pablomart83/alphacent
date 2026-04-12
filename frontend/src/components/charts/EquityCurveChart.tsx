import { type FC, useMemo } from 'react';
import {
  ComposedChart,
  Line,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts';
import { InteractiveChart, filterDataByPeriod } from './InteractiveChart';
import { PeriodSelector } from './PeriodSelector';
import { Badge } from '../ui/Badge';
import {
  chartTheme,
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
} from '../../lib/design-tokens';

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

/**
 * Merge normalized portfolio, SPY, and alpha data into a single array
 * for the main chart.
 */
function buildChartData(
  equityData: Array<{ date: string; equity: number }>,
  spyData: Array<{ date: string; close: number }> | undefined,
  period: string,
) {
  // Filter equity data by period first
  const filteredEquity = filterDataByPeriod(
    equityData.map((d) => ({ ...d })),
    'date',
    period,
  );

  // Normalize portfolio
  const normPortfolio = normalizeToBase100(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );

  const hasSpy = spyData && spyData.length > 0;

  if (!hasSpy) {
    // No SPY — return portfolio-only data
    const mainData = normPortfolio.map((d) => ({
      date: d.date,
      portfolio: d.value,
      spy: null as number | null,
      alpha: null as number | null,
      alphaPositive: null as number | null,
      alphaNegative: null as number | null,
    }));

    const drawdownData = computeDrawdown(
      filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
    );

    return { mainData, drawdownData, hasSpy: false };
  }

  // Build a date→spy map for alignment
  const spyMap = new Map<string, number>();
  for (const s of spyData) {
    spyMap.set(s.date, s.close);
  }

  // Filter SPY to match equity dates within the period
  const alignedSpy: Array<{ date: string; value: number }> = [];
  for (const d of filteredEquity) {
    const spyVal = spyMap.get(d.date);
    if (spyVal !== undefined) {
      alignedSpy.push({ date: d.date, value: spyVal });
    }
  }

  const normSpy = normalizeToBase100(alignedSpy);
  const spyNormMap = new Map<string, number>();
  for (const s of normSpy) {
    spyNormMap.set(s.date, s.value);
  }

  const mainData = normPortfolio.map((d) => {
    const spyVal = spyNormMap.get(d.date) ?? null;
    const alphaVal =
      spyVal !== null ? d.value - spyVal : null;
    return {
      date: d.date,
      portfolio: d.value,
      spy: spyVal,
      alpha: alphaVal,
      // Split alpha into positive/negative for conditional fill
      alphaPositive: alphaVal !== null && alphaVal >= 0 ? alphaVal : null,
      alphaNegative: alphaVal !== null && alphaVal < 0 ? alphaVal : null,
    };
  });

  const drawdownData = computeDrawdown(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );

  return { mainData, drawdownData, hasSpy: true };
}

// ── Custom Tooltip ─────────────────────────────────────────────────────────

interface TooltipPayloadEntry {
  dataKey: string;
  value: number | null;
  color: string;
}

interface CustomTooltipProps {
  active?: boolean;
  payload?: TooltipPayloadEntry[];
  label?: string;
  hasSpy: boolean;
}

const EquityCurveTooltip: FC<CustomTooltipProps> = ({
  active,
  payload,
  label,
  hasSpy,
}) => {
  if (!active || !payload || payload.length === 0) return null;

  const portfolioEntry = payload.find((p) => p.dataKey === 'portfolio');
  const spyEntry = payload.find((p) => p.dataKey === 'spy');

  const portfolioVal = portfolioEntry?.value ?? null;
  const spyVal = spyEntry?.value ?? null;
  const alpha =
    portfolioVal !== null && spyVal !== null
      ? portfolioVal - spyVal
      : null;

  return (
    <div
      style={{
        ...chartTooltipStyle,
        padding: '8px 12px',
        fontFamily: chartTheme.fontFamily,
        fontSize: 11,
      }}
    >
      <p style={{ color: '#f3f4f6', marginBottom: 4 }}>{label}</p>
      {portfolioVal !== null && (
        <p style={{ color: chartTheme.series.portfolio }}>
          Portfolio: {portfolioVal.toFixed(2)}
        </p>
      )}
      {hasSpy && spyVal !== null && (
        <p style={{ color: chartTheme.series.benchmark }}>
          SPY: {spyVal.toFixed(2)}
        </p>
      )}
      {hasSpy && alpha !== null && (
        <p
          style={{
            color: alpha >= 0 ? chartTheme.series.alpha : chartTheme.series.drawdown,
          }}
        >
          Alpha: {alpha >= 0 ? '+' : ''}
          {alpha.toFixed(2)}%
        </p>
      )}
    </div>
  );
};

// ── Main Component ─────────────────────────────────────────────────────────

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'];

export const EquityCurveChart: FC<EquityCurveChartProps> = ({
  equityData,
  spyData,
  period,
  onPeriodChange,
  height = 400,
}) => {
  const { mainData, drawdownData, hasSpy } = useMemo(
    () => buildChartData(equityData, spyData, period),
    [equityData, spyData, period],
  );

  const numericHeight = typeof height === 'number' ? height : 400;
  const drawdownHeight = Math.round(numericHeight / 3);
  const benchmarkUnavailable = !spyData || spyData.length === 0;
  const fillParent = height === '100%';

  return (
    <div className={fillParent ? 'w-full h-full flex flex-col' : 'w-full'}>
      {/* Header: Period selector + benchmark badge */}
      <div className="flex items-center justify-between mb-1 shrink-0">
        <PeriodSelector
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
        <InteractiveChart
          data={mainData}
          dataKeys={[]}
          xAxisKey="date"
          height={fillParent ? '100%' : numericHeight}
          showCrosshair={false}
          showZoom={true}
          showGrid={true}
        >
        {/* Alpha shading — positive (green) */}
        <Area
          type="monotone"
          dataKey="alphaPositive"
          stroke="none"
          fill={chartTheme.series.alpha}
          fillOpacity={0.15}
          baseLine={0}
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />
        {/* Alpha shading — negative (red) */}
        <Area
          type="monotone"
          dataKey="alphaNegative"
          stroke="none"
          fill={chartTheme.series.drawdown}
          fillOpacity={0.15}
          baseLine={0}
          dot={false}
          activeDot={false}
          isAnimationActive={false}
        />
        {/* SPY benchmark line (dashed gray) */}
        {hasSpy && (
          <Line
            type="monotone"
            dataKey="spy"
            stroke={chartTheme.series.benchmark}
            strokeWidth={1.5}
            strokeDasharray="6 3"
            dot={false}
            activeDot={{ r: 3, fill: chartTheme.series.benchmark }}
            isAnimationActive={false}
          />
        )}
        {/* Portfolio equity line (solid blue) */}
        <Line
          type="monotone"
          dataKey="portfolio"
          stroke={chartTheme.series.portfolio}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 3, fill: chartTheme.series.portfolio }}
          isAnimationActive={false}
        />
        {/* Custom tooltip with alpha display */}
        <Tooltip
          content={<EquityCurveTooltip hasSpy={hasSpy} />}
          cursor={{ stroke: '#9ca3af', strokeDasharray: '3 3' }}
        />
      </InteractiveChart>
      </div>

      {/* Drawdown sub-chart */}
      <div className="mt-1 shrink-0">
        <ResponsiveContainer width="100%" height={fillParent ? 80 : drawdownHeight}>
          <ComposedChart data={drawdownData}>
            <CartesianGrid {...chartGridProps} />
            <XAxis
              dataKey="date"
              {...chartAxisProps}
            />
            <YAxis
              {...chartAxisProps}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
            />
            <Tooltip
              contentStyle={{
                ...chartTooltipStyle,
                fontFamily: chartTheme.fontFamily,
                fontSize: 11,
              }}
              cursor={{ stroke: '#9ca3af', strokeDasharray: '3 3' }}
              formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(2)}%`, 'Drawdown']}
              labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
            />
            <ReferenceLine y={0} stroke={chartTheme.grid} strokeDasharray="3 3" />
            <Area
              type="monotone"
              dataKey="drawdown"
              stroke={chartTheme.series.drawdown}
              fill={chartTheme.series.drawdown}
              fillOpacity={0.4}
              strokeWidth={1}
              dot={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};

export { normalizeToBase100, computeDrawdown };
export type { EquityCurveChartProps };
