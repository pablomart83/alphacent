import {
  type FC,
  type ReactNode,
  useState,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import {
  ComposedChart,
  Line,
  Area,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceArea,
  ResponsiveContainer,
} from 'recharts';
import { subWeeks, subMonths, subYears, parseISO, isAfter } from 'date-fns';
import { PeriodSelector } from './PeriodSelector';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
} from '../../lib/design-tokens';

// ── Types ──────────────────────────────────────────────────────────────────

export interface DataKeyConfig {
  key: string;
  color: string;
  type: 'line' | 'area' | 'bar';
  strokeDasharray?: string;
}

export interface InteractiveChartProps {
  data: Array<Record<string, unknown>>;
  dataKeys: DataKeyConfig[];
  xAxisKey: string;
  periods?: string[];
  defaultPeriod?: string;
  onPeriodChange?: (period: string) => void;
  height?: number;
  showCrosshair?: boolean;
  showZoom?: boolean;
  showGrid?: boolean;
  tooltipFormatter?: (value: number, name: string) => [string, string];
  xAxisFormatter?: (value: string) => string;
  yAxisFormatter?: (value: number) => string;
  children?: ReactNode;
}

// ── Helpers ────────────────────────────────────────────────────────────────

/**
 * Compute the start-date cutoff for a given period string relative to an
 * anchor date (typically the last data point).
 */
export function periodStartDate(period: string, anchor: Date): Date | null {
  switch (period) {
    case '1W':
      return subWeeks(anchor, 1);
    case '1M':
      return subMonths(anchor, 1);
    case '3M':
      return subMonths(anchor, 3);
    case '6M':
      return subMonths(anchor, 6);
    case '1Y':
      return subYears(anchor, 1);
    case 'ALL':
    default:
      return null; // no filtering
  }
}

/**
 * Filter data array by period. Returns the full array when period is ALL or
 * when the data has no parseable dates.
 */
export function filterDataByPeriod<T extends Record<string, unknown>>(
  data: T[],
  xAxisKey: string,
  period: string,
): T[] {
  if (period === 'ALL' || data.length === 0) return data;

  const lastDateStr = String(data[data.length - 1][xAxisKey]);
  const anchor = parseISO(lastDateStr);
  if (isNaN(anchor.getTime())) return data;

  const start = periodStartDate(period, anchor);
  if (!start) return data;

  return data.filter((d) => {
    const dateStr = String(d[xAxisKey]);
    const date = parseISO(dateStr);
    return !isNaN(date.getTime()) && isAfter(date, start);
  });
}

// ── Component ──────────────────────────────────────────────────────────────

export const InteractiveChart: FC<InteractiveChartProps> = ({
  data,
  dataKeys,
  xAxisKey,
  periods,
  defaultPeriod = 'ALL',
  onPeriodChange,
  height = 300,
  showCrosshair = true,
  showZoom = true,
  showGrid = true,
  tooltipFormatter,
  xAxisFormatter,
  yAxisFormatter,
  children,
}) => {
  // ── Period state ───────────────────────────────────────────────────────
  const [activePeriod, setActivePeriod] = useState(defaultPeriod);

  const handlePeriodChange = useCallback(
    (period: string) => {
      setActivePeriod(period);
      // Reset zoom when period changes
      setZoomLeft(null);
      setZoomRight(null);
      setZoomedData(null);
      onPeriodChange?.(period);
    },
    [onPeriodChange],
  );

  // ── Period-filtered data ───────────────────────────────────────────────
  const periodData = useMemo(
    () => filterDataByPeriod(data, xAxisKey, activePeriod),
    [data, xAxisKey, activePeriod],
  );

  // ── Zoom state ─────────────────────────────────────────────────────────
  const [refAreaLeft, setRefAreaLeft] = useState<string | null>(null);
  const [refAreaRight, setRefAreaRight] = useState<string | null>(null);
  const [zoomedData, setZoomedData] = useState<Array<Record<string, unknown>> | null>(null);
  const [zoomLeft, setZoomLeft] = useState<string | null>(null);
  const [zoomRight, setZoomRight] = useState<string | null>(null);

  // ── Pan state ──────────────────────────────────────────────────────────
  const isPanning = useRef(false);
  const panStartX = useRef<number>(0);

  const isZoomed = zoomedData !== null;
  const displayData = zoomedData ?? periodData;

  // ── Recharts handler param type ─────────────────────────────────────────
  type ChartMouseEvent = {
    activeLabel?: string | number;
    activeCoordinate?: { x: number; y: number };
    chartX?: number;
  };

  // ── Zoom handlers ──────────────────────────────────────────────────────
  const handleMouseDown = useCallback(
    (e: ChartMouseEvent) => {
      if (!showZoom) return;
      if (e?.activeLabel == null) return;
      const label = String(e.activeLabel);

      if (isZoomed) {
        // Start panning
        isPanning.current = true;
        panStartX.current = e.chartX ?? 0;
        return;
      }

      setRefAreaLeft(label);
      setRefAreaRight(label);
    },
    [showZoom, isZoomed],
  );

  const handleMouseMove = useCallback(
    (e: ChartMouseEvent) => {
      if (e?.activeLabel == null) return;
      const label = String(e.activeLabel);

      // Panning while zoomed
      if (isPanning.current && isZoomed) {
        const dx = (e.chartX ?? 0) - panStartX.current;
        if (Math.abs(dx) < 5) return; // dead zone

        const source = periodData;
        const currentStart = source.findIndex(
          (d) => String(d[xAxisKey]) === zoomLeft,
        );
        const currentEnd = source.findIndex(
          (d) => String(d[xAxisKey]) === zoomRight,
        );
        if (currentStart === -1 || currentEnd === -1) return;

        const windowSize = currentEnd - currentStart;
        const shift = dx < 0 ? 1 : -1; // drag left → shift right in data

        const newStart = Math.max(0, Math.min(currentStart + shift, source.length - windowSize - 1));
        const newEnd = newStart + windowSize;

        if (newEnd < source.length) {
          const newLeft = String(source[newStart][xAxisKey]);
          const newRight = String(source[newEnd][xAxisKey]);
          setZoomLeft(newLeft);
          setZoomRight(newRight);
          setZoomedData(source.slice(newStart, newEnd + 1));
          panStartX.current = e.chartX ?? 0;
        }
        return;
      }

      // Drag-to-zoom selection
      if (refAreaLeft) {
        setRefAreaRight(label);
      }
    },
    [refAreaLeft, isZoomed, periodData, xAxisKey, zoomLeft, zoomRight],
  );

  const handleMouseUp = useCallback(() => {
    if (isPanning.current) {
      isPanning.current = false;
      return;
    }

    if (!refAreaLeft || !refAreaRight || refAreaLeft === refAreaRight) {
      setRefAreaLeft(null);
      setRefAreaRight(null);
      return;
    }

    // Determine left/right boundaries
    const source = periodData;
    const idxLeft = source.findIndex((d) => String(d[xAxisKey]) === refAreaLeft);
    const idxRight = source.findIndex((d) => String(d[xAxisKey]) === refAreaRight);

    if (idxLeft === -1 || idxRight === -1) {
      setRefAreaLeft(null);
      setRefAreaRight(null);
      return;
    }

    const startIdx = Math.min(idxLeft, idxRight);
    const endIdx = Math.max(idxLeft, idxRight);

    if (endIdx - startIdx < 1) {
      setRefAreaLeft(null);
      setRefAreaRight(null);
      return;
    }

    const sliced = source.slice(startIdx, endIdx + 1);
    setZoomedData(sliced);
    setZoomLeft(String(source[startIdx][xAxisKey]));
    setZoomRight(String(source[endIdx][xAxisKey]));
    setRefAreaLeft(null);
    setRefAreaRight(null);
  }, [refAreaLeft, refAreaRight, periodData, xAxisKey]);

  const handleResetZoom = useCallback(() => {
    setZoomedData(null);
    setZoomLeft(null);
    setZoomRight(null);
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="w-full">
      {/* Header row: period selector + reset zoom */}
      <div className="flex items-center justify-between mb-2">
        {periods ? (
          <PeriodSelector
            periods={periods}
            activePeriod={activePeriod}
            onPeriodChange={handlePeriodChange}
          />
        ) : (
          <div />
        )}

        {isZoomed && (
          <button
            type="button"
            onClick={handleResetZoom}
            className="px-2 py-0.5 text-xs font-mono rounded bg-dark-hover text-text-secondary hover:text-text-primary transition-colors"
          >
            Reset Zoom
          </button>
        )}
      </div>

      {/* Chart */}
      <div className="min-h-[200px]">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart
          data={displayData}
          onMouseDown={handleMouseDown as never}
          onMouseMove={handleMouseMove as never}
          onMouseUp={handleMouseUp as never}
          style={{ cursor: isZoomed ? 'grab' : showZoom ? 'crosshair' : 'default' }}
        >
          {showGrid && <CartesianGrid {...chartGridProps} />}

          <XAxis
            dataKey={xAxisKey}
            {...chartAxisProps}
            tickFormatter={xAxisFormatter}
          />
          <YAxis
            {...chartAxisProps}
            tickFormatter={yAxisFormatter}
          />

          {showCrosshair && (
            <Tooltip
              contentStyle={{
                ...chartTooltipStyle,
                fontFamily: chartTheme.fontFamily,
                fontSize: chartTheme.axisFontSize + 1,
              }}
              cursor={{ stroke: '#9ca3af', strokeDasharray: '3 3' }}
              formatter={tooltipFormatter as never}
              labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
            />
          )}

          {/* Dynamic series rendering */}
          {dataKeys.map((dk) => {
            switch (dk.type) {
              case 'line':
                return (
                  <Line
                    key={dk.key}
                    type="monotone"
                    dataKey={dk.key}
                    stroke={dk.color}
                    strokeWidth={1.5}
                    strokeDasharray={dk.strokeDasharray}
                    dot={false}
                    activeDot={{ r: 3, fill: dk.color }}
                  />
                );
              case 'area':
                return (
                  <Area
                    key={dk.key}
                    type="monotone"
                    dataKey={dk.key}
                    stroke={dk.color}
                    fill={dk.color}
                    fillOpacity={0.15}
                    strokeWidth={1.5}
                    dot={false}
                    activeDot={{ r: 3, fill: dk.color }}
                  />
                );
              case 'bar':
                return (
                  <Bar
                    key={dk.key}
                    dataKey={dk.key}
                    fill={dk.color}
                    fillOpacity={0.8}
                  />
                );
              default:
                return null;
            }
          })}

          {/* Zoom selection overlay */}
          {refAreaLeft && refAreaRight && refAreaLeft !== refAreaRight && (
            <ReferenceArea
              x1={refAreaLeft}
              x2={refAreaRight}
              strokeOpacity={0.3}
              fill="#3b82f6"
              fillOpacity={0.15}
            />
          )}

          {/* Custom children (ReferenceLine, ReferenceArea, etc.) */}
          {children}
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
};
