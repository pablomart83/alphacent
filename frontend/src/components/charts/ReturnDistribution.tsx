import { type FC, useMemo, useState, useRef, useCallback, useEffect } from 'react';
import { Badge } from '../ui/Badge';

interface ReturnDistributionProps {
  data: Array<{ bin: number; count: number }>;
  skew: number;
  kurtosis: number;
  height?: number;
}

/**
 * Compute a normal distribution overlay for the histogram bins.
 */
function computeNormalOverlay(
  data: Array<{ bin: number; count: number }>,
): Array<{ bin: number; count: number; normal: number }> {
  if (data.length === 0) return [];

  const totalCount = data.reduce((s, d) => s + d.count, 0);
  if (totalCount === 0) return data.map((d) => ({ ...d, normal: 0 }));

  const mean = data.reduce((s, d) => s + d.bin * d.count, 0) / totalCount;
  const variance =
    data.reduce((s, d) => s + d.count * (d.bin - mean) ** 2, 0) / totalCount;
  const std = Math.sqrt(variance) || 1;

  const binWidth =
    data.length > 1 ? Math.abs(data[1].bin - data[0].bin) : 1;

  return data.map((d) => {
    const z = (d.bin - mean) / std;
    const pdf = (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * z * z);
    const normal = pdf * totalCount * binWidth;
    return { ...d, normal: Math.round(normal * 100) / 100 };
  });
}

interface TooltipState {
  x: number;
  y: number;
  bin: number;
  count: number;
  normal: number;
}

export const ReturnDistribution: FC<ReturnDistributionProps> = ({
  data,
  skew,
  kurtosis,
  height = 300,
}) => {
  const chartData = useMemo(() => computeNormalOverlay(data), [data]);
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

  const maxCount = useMemo(
    () => Math.max(...chartData.map((d) => Math.max(d.count, d.normal)), 1),
    [chartData],
  );

  const handleMouseEnter = useCallback(
    (d: (typeof chartData)[0], rect: SVGRectElement) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      const rr = rect.getBoundingClientRect();
      setTooltip({
        x: rr.left - cr.left + rr.width / 2,
        y: rr.top - cr.top - 8,
        bin: d.bin,
        count: d.count,
        normal: d.normal,
      });
    },
    [],
  );

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground font-mono text-sm">
        No return distribution data available
      </div>
    );
  }

  const margin = { top: 10, right: 10, bottom: 30, left: 40 };
  const chartW = svgW - margin.left - margin.right;
  const chartH = height - margin.top - margin.bottom;

  // Build normal curve path
  const normalPath = chartData
    .map((d, i) => {
      const x = margin.left + (i / chartData.length) * chartW + chartW / chartData.length / 2;
      const y = margin.top + chartH - (d.normal / maxCount) * chartH;
      return `${i === 0 ? 'M' : 'L'} ${x} ${y}`;
    })
    .join(' ');

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Badge variant="outline">
          <span className="font-mono text-xs">Skew: {skew.toFixed(2)}</span>
        </Badge>
        <Badge variant="outline">
          <span className="font-mono text-xs">Kurtosis: {kurtosis.toFixed(2)}</span>
        </Badge>
      </div>
      <div ref={containerRef} className="relative min-h-[200px] w-full" style={{ height }}>
        <svg width={svgW} height={height}>
          {/* Grid lines */}
          {[0, 0.25, 0.5, 0.75, 1].map((frac) => {
            const y = margin.top + (1 - frac) * chartH;
            const val = frac * maxCount;
            return (
              <g key={frac}>
                <line x1={margin.left} y1={y} x2={svgW - margin.right} y2={y} stroke="#1f2937" strokeDasharray="3 3" />
                <text x={margin.left - 4} y={y + 3} textAnchor="end" fill="#9ca3af" fontSize={11} fontFamily="'JetBrains Mono', monospace">
                  {val.toFixed(0)}
                </text>
              </g>
            );
          })}

          {/* Bars */}
          {chartData.map((d, i) => {
            const barW = Math.max(2, chartW / chartData.length - 2);
            const x = margin.left + (i / chartData.length) * chartW + 1;
            const barH = (d.count / maxCount) * chartH;
            const y = margin.top + chartH - barH;

            return (
              <g key={i}>
                <rect
                  x={x}
                  y={y}
                  width={barW}
                  height={Math.max(0, barH)}
                  rx={2}
                  fill="#3b82f6"
                  fillOpacity={0.7}
                  onMouseEnter={(e) => handleMouseEnter(d, e.currentTarget)}
                  onMouseLeave={() => setTooltip(null)}
                  className="cursor-pointer"
                />
                <text
                  x={x + barW / 2}
                  y={height - margin.bottom + 14}
                  textAnchor="middle"
                  fill="#9ca3af"
                  fontSize={Math.min(11, svgW / chartData.length / 5)}
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {d.bin.toFixed(1)}%
                </text>
              </g>
            );
          })}

          {/* Normal curve overlay */}
          <path d={normalPath} fill="none" stroke="#eab308" strokeWidth={2} strokeDasharray="4 2" />
        </svg>

        {tooltip && (
          <div
            className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
            style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
          >
            <div className="text-gray-400 mb-0.5">Return: {tooltip.bin.toFixed(2)}%</div>
            <div>Count: {tooltip.count}</div>
            <div>Normal Dist.: {tooltip.normal.toFixed(1)}</div>
          </div>
        )}
      </div>
    </div>
  );
};

export type { ReturnDistributionProps };
