import {
  type FC,
  type ReactNode,
  useState,
  useCallback,
  useMemo,
  useRef,
} from 'react';
import { PeriodSelector } from './PeriodSelector';

// Re-export utilities so existing imports still work
export { filterDataByPeriod, periodStartDate } from '../../lib/chart-utils';

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
  height?: number | string;
  showCrosshair?: boolean;
  showZoom?: boolean;
  showGrid?: boolean;
  tooltipFormatter?: (value: number, name: string) => [string, string];
  xAxisFormatter?: (value: string) => string;
  yAxisFormatter?: (value: number) => string;
  children?: ReactNode;
}

// ── Helpers ────────────────────────────────────────────────────────────────

import { filterDataByPeriod } from '../../lib/chart-utils';

// ── Tooltip ────────────────────────────────────────────────────────────────

interface TooltipState {
  x: number;
  y: number;
  label: string;
  values: Array<{ name: string; value: string; color: string }>;
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
  showGrid = true,
  tooltipFormatter,
  xAxisFormatter,
  yAxisFormatter,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [activePeriod, setActivePeriod] = useState(defaultPeriod);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const handlePeriodChange = useCallback(
    (period: string) => {
      setActivePeriod(period);
      onPeriodChange?.(period);
    },
    [onPeriodChange],
  );

  const periodData = useMemo(
    () => filterDataByPeriod(data, xAxisKey, activePeriod),
    [data, xAxisKey, activePeriod],
  );

  const displayData = periodData;

  // Compute Y range across all series
  const { yMin, yMax } = useMemo(() => {
    let min = Infinity;
    let max = -Infinity;
    for (const d of displayData) {
      for (const dk of dataKeys) {
        const v = Number(d[dk.key]);
        if (!isNaN(v)) {
          min = Math.min(min, v);
          max = Math.max(max, v);
        }
      }
    }
    if (!isFinite(min)) min = 0;
    if (!isFinite(max)) max = 1;
    const pad = (max - min) * 0.1 || 0.1;
    return { yMin: min - pad, yMax: max + pad };
  }, [displayData, dataKeys]);

  const numH = typeof height === 'number' ? height : 300;
  const margin = { top: 10, right: 10, bottom: 30, left: 50 };
  const svgW = 600;
  const chartW = svgW - margin.left - margin.right;
  const chartH = numH - margin.top - margin.bottom;
  const yRange = yMax - yMin || 1;

  const toX = (i: number) => margin.left + (i / Math.max(displayData.length - 1, 1)) * chartW;
  const toY = (v: number) => margin.top + (1 - (v - yMin) / yRange) * chartH;

  const handleMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      const container = containerRef.current;
      if (!container || displayData.length === 0) return;
      const svgRect = e.currentTarget.getBoundingClientRect();
      const mouseX = ((e.clientX - svgRect.left) / svgRect.width) * svgW;
      const idx = Math.round(((mouseX - margin.left) / chartW) * (displayData.length - 1));
      const clampedIdx = Math.max(0, Math.min(displayData.length - 1, idx));
      const d = displayData[clampedIdx];
      if (!d) return;

      const label = xAxisFormatter
        ? xAxisFormatter(String(d[xAxisKey]))
        : String(d[xAxisKey]);

      const values = dataKeys.map((dk) => {
        const raw = Number(d[dk.key]) || 0;
        const [formatted, name] = tooltipFormatter
          ? tooltipFormatter(raw, dk.key)
          : [yAxisFormatter ? yAxisFormatter(raw) : raw.toFixed(2), dk.key];
        return { name, value: formatted, color: dk.color };
      });

      const cr = container.getBoundingClientRect();
      setTooltip({
        x: e.clientX - cr.left,
        y: e.clientY - cr.top - 12,
        label,
        values,
      });
    },
    [displayData, dataKeys, xAxisKey, xAxisFormatter, yAxisFormatter, tooltipFormatter, chartW, svgW],
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  // ── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="w-full">
      {periods && (
        <div className="flex items-center justify-between mb-2">
          <PeriodSelector
            periods={periods}
            activePeriod={activePeriod}
            onPeriodChange={handlePeriodChange}
          />
        </div>
      )}

      <div ref={containerRef} className="relative min-h-[200px] w-full" style={{ height: numH }}>
        <svg
          width="100%"
          height="100%"
          viewBox={`0 0 ${svgW} ${numH}`}
          preserveAspectRatio="xMidYMid meet"
          onMouseMove={handleMouseMove}
          onMouseLeave={handleMouseLeave}
        >
          {/* Grid */}
          {showGrid &&
            [0, 0.25, 0.5, 0.75, 1].map((frac) => {
              const y = margin.top + (1 - frac) * chartH;
              const val = yMin + frac * yRange;
              return (
                <g key={frac}>
                  <line x1={margin.left} y1={y} x2={svgW - margin.right} y2={y} stroke="#1f2937" strokeDasharray="3 3" />
                  <text x={margin.left - 4} y={y + 3} textAnchor="end" fill="#9ca3af" fontSize={9} fontFamily="monospace">
                    {yAxisFormatter ? yAxisFormatter(val) : val.toFixed(2)}
                  </text>
                </g>
              );
            })}

          {/* Series */}
          {dataKeys.map((dk) => {
            const points = displayData
              .map((d, i) => {
                const v = Number(d[dk.key]);
                if (isNaN(v)) return null;
                return { x: toX(i), y: toY(v) };
              })
              .filter(Boolean) as Array<{ x: number; y: number }>;

            if (points.length === 0) return null;

            const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'} ${p.x} ${p.y}`).join(' ');

            if (dk.type === 'bar') {
              const barW = Math.max(2, chartW / displayData.length - 2);
              return (
                <g key={dk.key}>
                  {displayData.map((d, i) => {
                    const v = Number(d[dk.key]);
                    if (isNaN(v)) return null;
                    const barH = Math.abs(((v - yMin) / yRange) * chartH);
                    const barY = toY(Math.max(v, 0));
                    return (
                      <rect
                        key={i}
                        x={toX(i) - barW / 2}
                        y={barY}
                        width={barW}
                        height={Math.max(0, barH)}
                        fill={dk.color}
                        fillOpacity={0.8}
                        rx={1}
                      />
                    );
                  })}
                </g>
              );
            }

            if (dk.type === 'area') {
              const areaD = `${pathD} L ${points[points.length - 1].x} ${margin.top + chartH} L ${points[0].x} ${margin.top + chartH} Z`;
              return (
                <g key={dk.key}>
                  <path d={areaD} fill={dk.color} fillOpacity={0.15} />
                  <path d={pathD} fill="none" stroke={dk.color} strokeWidth={1.5} />
                </g>
              );
            }

            // line
            return (
              <path
                key={dk.key}
                d={pathD}
                fill="none"
                stroke={dk.color}
                strokeWidth={1.5}
                strokeDasharray={dk.strokeDasharray}
              />
            );
          })}

          {/* X-axis labels */}
          {displayData.length > 0 &&
            displayData
              .filter((_, i) => {
                const step = Math.max(1, Math.floor(displayData.length / 8));
                return i % step === 0 || i === displayData.length - 1;
              })
              .map((d, _) => {
                const idx = displayData.indexOf(d);
                const x = toX(idx);
                const label = xAxisFormatter
                  ? xAxisFormatter(String(d[xAxisKey]))
                  : String(d[xAxisKey]);
                return (
                  <text
                    key={idx}
                    x={x}
                    y={numH - margin.bottom + 14}
                    textAnchor="middle"
                    fill="#9ca3af"
                    fontSize={8}
                    fontFamily="monospace"
                  >
                    {label.length > 10 ? label.slice(5, 10) : label}
                  </text>
                );
              })}
        </svg>

        {tooltip && (
          <div
            className="absolute pointer-events-none z-50 px-2 py-1.5 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
            style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
          >
            <div className="text-gray-400 mb-0.5">{tooltip.label}</div>
            {tooltip.values.map((v) => (
              <div key={v.name} className="flex items-center gap-1.5">
                <div className="w-2 h-2 rounded-full" style={{ backgroundColor: v.color }} />
                <span>{v.name}: {v.value}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
