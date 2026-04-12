import { type FC, useMemo, useState, useRef, useCallback } from 'react';

interface BarDatum {
  label: string;
  value: number;
  color?: string;
}

interface SVGBarChartProps {
  data: BarDatum[];
  height?: number;
  /** Default bar color */
  color?: string;
  /** Show value labels on bars */
  showValues?: boolean;
  /** Format value for tooltip / label */
  formatValue?: (v: number) => string;
  /** Horizontal layout (bars go left-to-right) */
  horizontal?: boolean;
  /** Stacked bar data: each item has label + multiple named values */
  className?: string;
}

interface TooltipState {
  x: number;
  y: number;
  label: string;
  value: string;
}

/**
 * Minimal SVG bar chart — no Recharts dependency.
 */
export const SVGBarChart: FC<SVGBarChartProps> = ({
  data,
  height = 250,
  color = '#3b82f6',
  formatValue = (v) => v.toFixed(1),
  horizontal = false,
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const maxVal = useMemo(() => {
    const vals = data.map((d) => Math.abs(d.value));
    return Math.max(...vals, 0.001);
  }, [data]);

  const minVal = useMemo(() => {
    return Math.min(...data.map((d) => d.value), 0);
  }, [data]);

  const handleMouseEnter = useCallback(
    (d: BarDatum, rect: SVGRectElement) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      const rr = rect.getBoundingClientRect();
      setTooltip({
        x: rr.left - cr.left + rr.width / 2,
        y: rr.top - cr.top - 8,
        label: d.label,
        value: formatValue(d.value),
      });
    },
    [formatValue],
  );

  const handleMouseLeave = useCallback(() => setTooltip(null), []);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-xs font-mono" style={{ height }}>
        No data
      </div>
    );
  }

  if (horizontal) {
    // Horizontal bars
    const barH = Math.min(24, (height - 20) / data.length - 4);
    const svgH = Math.max(height, data.length * (barH + 4) + 20);
    const labelW = 60;

    return (
      <div ref={containerRef} className={`relative w-full ${className || ''}`} style={{ height: svgH }}>
        <svg width="100%" height="100%" viewBox={`0 0 300 ${svgH}`} preserveAspectRatio="none">
          {data.map((d, i) => {
            const y = i * (barH + 4) + 10;
            const barWidth = maxVal > 0 ? (Math.abs(d.value) / maxVal) * (300 - labelW - 10) : 0;
            return (
              <g key={i}>
                <text x={labelW - 4} y={y + barH / 2 + 3} textAnchor="end" fill="#9ca3af" fontSize={9} fontFamily="monospace">
                  {d.label}
                </text>
                <rect
                  x={labelW}
                  y={y}
                  width={barWidth}
                  height={barH}
                  rx={3}
                  fill={d.color || color}
                  fillOpacity={0.8}
                  onMouseEnter={(e) => handleMouseEnter(d, e.currentTarget)}
                  onMouseLeave={handleMouseLeave}
                  className="cursor-pointer transition-opacity hover:opacity-100"
                />
                <text x={labelW + barWidth + 4} y={y + barH / 2 + 3} fill="#9ca3af" fontSize={8} fontFamily="monospace">
                  {formatValue(d.value)}
                </text>
              </g>
            );
          })}
        </svg>
        {tooltip && (
          <div
            className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
            style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
          >
            {tooltip.label}: {tooltip.value}
          </div>
        )}
      </div>
    );
  }

  // Vertical bars
  const margin = { top: 10, right: 10, bottom: 30, left: 40 };
  const hasNegative = minVal < 0;
  const range = hasNegative ? maxVal - minVal : maxVal;

  return (
    <div ref={containerRef} className={`relative w-full ${className || ''}`} style={{ height }}>
      <svg width="100%" height="100%" viewBox={`0 0 500 ${height}`} preserveAspectRatio="none">
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = margin.top + (1 - frac) * (height - margin.top - margin.bottom);
          const val = hasNegative ? minVal + frac * range : frac * maxVal;
          return (
            <g key={frac}>
              <line x1={margin.left} y1={y} x2={500 - margin.right} y2={y} stroke="#1f2937" strokeDasharray="3 3" />
              <text x={margin.left - 4} y={y + 3} textAnchor="end" fill="#9ca3af" fontSize={9} fontFamily="monospace">
                {formatValue(val)}
              </text>
            </g>
          );
        })}

        {/* Zero line if negative values */}
        {hasNegative && (() => {
          const zeroY = margin.top + (1 - (0 - minVal) / range) * (height - margin.top - margin.bottom);
          return <line x1={margin.left} y1={zeroY} x2={500 - margin.right} y2={zeroY} stroke="#4b5563" strokeWidth={1} />;
        })()}

        {/* Bars */}
        {data.map((d, i) => {
          const chartWidth = 500 - margin.left - margin.right;
          const barWidth = Math.max(2, chartWidth / data.length - 2);
          const x = margin.left + (i / data.length) * chartWidth + 1;
          const chartHeight = height - margin.top - margin.bottom;

          let barHeight: number;
          let barY: number;

          if (hasNegative) {
            const zeroY = margin.top + (1 - (0 - minVal) / range) * chartHeight;
            if (d.value >= 0) {
              barHeight = (d.value / range) * chartHeight;
              barY = zeroY - barHeight;
            } else {
              barHeight = (Math.abs(d.value) / range) * chartHeight;
              barY = zeroY;
            }
          } else {
            barHeight = maxVal > 0 ? (d.value / maxVal) * chartHeight : 0;
            barY = margin.top + chartHeight - barHeight;
          }

          return (
            <g key={i}>
              <rect
                x={x}
                y={barY}
                width={barWidth}
                height={Math.max(0, barHeight)}
                rx={2}
                fill={d.color || color}
                fillOpacity={0.8}
                onMouseEnter={(e) => handleMouseEnter(d, e.currentTarget)}
                onMouseLeave={handleMouseLeave}
                className="cursor-pointer transition-opacity hover:opacity-100"
              />
              {/* X-axis label */}
              <text
                x={x + barWidth / 2}
                y={height - margin.bottom + 14}
                textAnchor="middle"
                fill="#9ca3af"
                fontSize={Math.min(9, 500 / data.length / 6)}
                fontFamily="monospace"
                transform={data.length > 8 ? `rotate(-45, ${x + barWidth / 2}, ${height - margin.bottom + 14})` : undefined}
              >
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
      {tooltip && (
        <div
          className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
        >
          {tooltip.label}: {tooltip.value}
        </div>
      )}
    </div>
  );
};
