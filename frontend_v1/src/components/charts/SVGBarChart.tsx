import { type FC, useMemo, useState, useRef, useCallback, useEffect } from 'react';

interface BarDatum {
  label: string;
  value: number;
  color?: string;
}

interface SVGBarChartProps {
  data: BarDatum[];
  height?: number;
  color?: string;
  showValues?: boolean;
  formatValue?: (v: number) => string;
  horizontal?: boolean;
  className?: string;
}

interface TooltipState {
  x: number;
  y: number;
  label: string;
  value: string;
}

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
  const [svgW, setSvgW] = useState(500);

  // Track container width
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const e of entries) {
        const w = Math.round(e.contentRect.width);
        if (w > 0) setSvgW(w);
      }
    });
    ro.observe(el);
    setSvgW(el.clientWidth || 500);
    return () => ro.disconnect();
  }, []);

  const maxVal = useMemo(() => Math.max(...data.map((d) => Math.abs(d.value)), 0.001), [data]);
  const minVal = useMemo(() => Math.min(...data.map((d) => d.value), 0), [data]);

  const handleMouseEnter = useCallback(
    (d: BarDatum, rect: SVGRectElement) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      const rr = rect.getBoundingClientRect();
      setTooltip({ x: rr.left - cr.left + rr.width / 2, y: rr.top - cr.top - 8, label: d.label, value: formatValue(d.value) });
    },
    [formatValue],
  );

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-xs font-mono" style={{ height }}>
        No data
      </div>
    );
  }

  if (horizontal) {
    const barH = Math.min(24, (height - 20) / data.length - 4);
    const svgH = Math.max(height, data.length * (barH + 4) + 20);
    const labelW = 70;

    return (
      <div ref={containerRef} className={`relative w-full ${className || ''}`} style={{ height: svgH }}>
        <svg width={svgW} height={svgH}>
          {data.map((d, i) => {
            const y = i * (barH + 4) + 10;
            const barWidth = maxVal > 0 ? (Math.abs(d.value) / maxVal) * (svgW - labelW - 20) : 0;
            return (
              <g key={i}>
                <text x={labelW - 4} y={y + barH / 2 + 3} textAnchor="end" fill="#9ca3af" fontSize={11} fontFamily="'JetBrains Mono', monospace">
                  {d.label}
                </text>
                <rect x={labelW} y={y} width={barWidth} height={barH} rx={3}
                  fill={d.color || color} fillOpacity={0.8}
                  onMouseEnter={(e) => handleMouseEnter(d, e.currentTarget)}
                  onMouseLeave={() => setTooltip(null)}
                  className="cursor-pointer hover:opacity-100" />
                <text x={labelW + barWidth + 4} y={y + barH / 2 + 3} fill="#9ca3af" fontSize={10} fontFamily="'JetBrains Mono', monospace">
                  {formatValue(d.value)}
                </text>
              </g>
            );
          })}
        </svg>
        {tooltip && (
          <div className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
            style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}>
            {tooltip.label}: {tooltip.value}
          </div>
        )}
      </div>
    );
  }

  // Vertical bars — render at actual pixel dimensions, no viewBox scaling
  const margin = { top: 10, right: 10, bottom: 35, left: 50 };
  const hasNegative = minVal < 0;
  const range = hasNegative ? maxVal - minVal : maxVal;
  const chartW = svgW - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;

  return (
    <div ref={containerRef} className={`relative w-full ${className || ''}`} style={{ height }}>
      <svg width={svgW} height={height}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
          const y = margin.top + (1 - frac) * chartH;
          const val = hasNegative ? minVal + frac * range : frac * maxVal;
          return (
            <g key={frac}>
              <line x1={margin.left} y1={y} x2={svgW - margin.right} y2={y} stroke="#1f2937" strokeDasharray="3 3" />
              <text x={margin.left - 4} y={y + 4} textAnchor="end" fill="#9ca3af" fontSize={11} fontFamily="'JetBrains Mono', monospace">
                {formatValue(val)}
              </text>
            </g>
          );
        })}

        {/* Zero line */}
        {hasNegative && (() => {
          const zeroY = margin.top + (1 - (0 - minVal) / range) * chartH;
          return <line x1={margin.left} y1={zeroY} x2={svgW - margin.right} y2={zeroY} stroke="#4b5563" strokeWidth={1} />;
        })()}

        {/* Bars */}
        {data.map((d, i) => {
          const gap = Math.max(2, Math.min(6, chartW / data.length * 0.15));
          const barWidth = Math.max(4, (chartW / data.length) - gap);
          const x = margin.left + (i / data.length) * chartW + gap / 2;

          let barHeight: number;
          let barY: number;

          if (hasNegative) {
            const zeroY = margin.top + (1 - (0 - minVal) / range) * chartH;
            if (d.value >= 0) {
              barHeight = (d.value / range) * chartH;
              barY = zeroY - barHeight;
            } else {
              barHeight = (Math.abs(d.value) / range) * chartH;
              barY = zeroY;
            }
          } else {
            barHeight = maxVal > 0 ? (d.value / maxVal) * chartH : 0;
            barY = margin.top + chartH - barHeight;
          }

          return (
            <g key={i}>
              <rect x={x} y={barY} width={barWidth} height={Math.max(0, barHeight)} rx={2}
                fill={d.color || color} fillOpacity={0.8}
                onMouseEnter={(e) => handleMouseEnter(d, e.currentTarget)}
                onMouseLeave={() => setTooltip(null)}
                className="cursor-pointer hover:opacity-100" />
              <text x={x + barWidth / 2} y={height - margin.bottom + 14} textAnchor="middle"
                fill="#9ca3af" fontSize={Math.min(11, chartW / data.length / 4)}
                fontFamily="'JetBrains Mono', monospace"
                transform={data.length > 8 ? `rotate(-45, ${x + barWidth / 2}, ${height - margin.bottom + 14})` : undefined}>
                {d.label}
              </text>
            </g>
          );
        })}
      </svg>
      {tooltip && (
        <div className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}>
          {tooltip.label}: {tooltip.value}
        </div>
      )}
    </div>
  );
};
