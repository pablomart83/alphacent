import { type FC, useMemo, useState, useRef, useCallback } from 'react';

interface StackedBarSeries {
  key: string;
  color: string;
  label: string;
}

interface SVGStackedBarChartProps {
  data: Array<Record<string, unknown>>;
  categoryKey: string;
  series: StackedBarSeries[];
  height?: number;
  formatValue?: (v: number) => string;
  showLegend?: boolean;
}

interface TooltipState {
  x: number;
  y: number;
  content: string;
}

export const SVGStackedBarChart: FC<SVGStackedBarChartProps> = ({
  data,
  categoryKey,
  series,
  height = 350,
  formatValue = (v) => `${v.toFixed(2)}%`,
  showLegend = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const { maxVal, minVal } = useMemo(() => {
    let max = 0;
    let min = 0;
    for (const d of data) {
      let posSum = 0;
      let negSum = 0;
      for (const s of series) {
        const v = Number(d[s.key]) || 0;
        if (v >= 0) posSum += v;
        else negSum += v;
      }
      max = Math.max(max, posSum);
      min = Math.min(min, negSum);
    }
    return { maxVal: max || 0.001, minVal: min };
  }, [data, series]);

  const handleMouseEnter = useCallback(
    (label: string, values: string, rect: SVGRectElement) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      const rr = rect.getBoundingClientRect();
      setTooltip({
        x: rr.left - cr.left + rr.width / 2,
        y: rr.top - cr.top - 8,
        content: `${label}\n${values}`,
      });
    },
    [],
  );

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-xs font-mono" style={{ height }}>
        No data
      </div>
    );
  }

  const margin = { top: 10, right: 10, bottom: 40, left: 50 };
  const range = maxVal - minVal || 0.001;
  const chartH = height - margin.top - margin.bottom;
  const legendH = showLegend ? 24 : 0;

  return (
    <div ref={containerRef} className="relative w-full" style={{ height: height + legendH }}>
      <svg width="100%" height={height} viewBox={`0 0 500 ${height}`} preserveAspectRatio="xMidYMid meet">
        {/* Grid */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = margin.top + (1 - frac) * chartH;
          const val = minVal + frac * range;
          return (
            <g key={frac}>
              <line x1={margin.left} y1={y} x2={500 - margin.right} y2={y} stroke="#1f2937" strokeDasharray="3 3" />
              <text x={margin.left - 4} y={y + 3} textAnchor="end" fill="#9ca3af" fontSize={9} fontFamily="monospace">
                {formatValue(val)}
              </text>
            </g>
          );
        })}

        {/* Stacked bars */}
        {data.map((d, i) => {
          const chartW = 500 - margin.left - margin.right;
          const barW = Math.max(4, chartW / data.length - 4);
          const x = margin.left + (i / data.length) * chartW + 2;
          const zeroY = margin.top + (1 - (0 - minVal) / range) * chartH;

          let posOffset = 0;
          let negOffset = 0;

          const valuesStr = series.map((s) => `${s.label}: ${formatValue(Number(d[s.key]) || 0)}`).join(', ');

          return (
            <g key={i}>
              {series.map((s) => {
                const v = Number(d[s.key]) || 0;
                const barHeight = (Math.abs(v) / range) * chartH;
                let barY: number;

                if (v >= 0) {
                  barY = zeroY - posOffset - barHeight;
                  posOffset += barHeight;
                } else {
                  barY = zeroY + negOffset;
                  negOffset += barHeight;
                }

                return (
                  <rect
                    key={s.key}
                    x={x}
                    y={barY}
                    width={barW}
                    height={Math.max(0, barHeight)}
                    fill={s.color}
                    fillOpacity={0.8}
                    onMouseEnter={(e) => handleMouseEnter(String(d[categoryKey]), valuesStr, e.currentTarget)}
                    onMouseLeave={() => setTooltip(null)}
                    className="cursor-pointer"
                  />
                );
              })}
              <text
                x={x + barW / 2}
                y={height - margin.bottom + 14}
                textAnchor="middle"
                fill="#9ca3af"
                fontSize={Math.min(9, 400 / data.length / 4)}
                fontFamily="monospace"
                transform={data.length > 6 ? `rotate(-45, ${x + barW / 2}, ${height - margin.bottom + 14})` : undefined}
              >
                {String(d[categoryKey])}
              </text>
            </g>
          );
        })}
      </svg>

      {/* Legend */}
      {showLegend && (
        <div className="flex items-center justify-center gap-4 mt-1">
          {series.map((s) => (
            <div key={s.key} className="flex items-center gap-1.5">
              <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
              <span className="text-[10px] text-gray-400 font-mono">{s.label}</span>
            </div>
          ))}
        </div>
      )}

      {tooltip && (
        <div
          className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-pre"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
        >
          {tooltip.content}
        </div>
      )}
    </div>
  );
};
