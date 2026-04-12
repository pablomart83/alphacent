import { type FC, useMemo, useState, useRef, useCallback } from 'react';

interface PieDatum {
  name: string;
  value: number;
}

interface SVGPieChartProps {
  data: PieDatum[];
  height?: number;
  colors?: string[];
  /** Inner radius for donut chart (0 = full pie) */
  innerRadius?: number;
  /** Show labels on slices */
  showLabels?: boolean;
  /** Format value for tooltip */
  formatValue?: (v: number) => string;
  className?: string;
}

const DEFAULT_COLORS = [
  '#3b82f6', '#22c55e', '#eab308', '#ef4444', '#8b5cf6',
  '#ec4899', '#14b8a6', '#f97316', '#6366f1', '#84cc16',
];

interface TooltipState {
  x: number;
  y: number;
  name: string;
  value: string;
}

/**
 * Minimal SVG pie/donut chart — no Recharts dependency.
 */
export const SVGPieChart: FC<SVGPieChartProps> = ({
  data,
  height = 200,
  colors = DEFAULT_COLORS,
  innerRadius = 0,
  showLabels = false,
  formatValue = (v) => v.toFixed(0),
  className,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [tooltip, setTooltip] = useState<TooltipState | null>(null);

  const total = useMemo(() => data.reduce((s, d) => s + d.value, 0), [data]);

  const handleMouseEnter = useCallback(
    (d: PieDatum, e: React.MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      setTooltip({
        x: e.clientX - cr.left,
        y: e.clientY - cr.top - 12,
        name: d.name,
        value: formatValue(d.value),
      });
    },
    [formatValue],
  );

  const handleMouseMove = useCallback(
    (d: PieDatum, e: React.MouseEvent) => {
      const container = containerRef.current;
      if (!container) return;
      const cr = container.getBoundingClientRect();
      setTooltip({
        x: e.clientX - cr.left,
        y: e.clientY - cr.top - 12,
        name: d.name,
        value: formatValue(d.value),
      });
    },
    [formatValue],
  );

  if (!data || data.length === 0 || total === 0) {
    return (
      <div className="flex items-center justify-center text-muted-foreground text-xs font-mono" style={{ height }}>
        No data
      </div>
    );
  }

  const size = Math.min(height, 300);
  const cx = size / 2;
  const cy = size / 2;
  const outerR = size / 2 - 4;
  const innerR = innerRadius > 0 ? innerRadius : 0;

  // Build arc paths
  let startAngle = -Math.PI / 2;
  const arcs = data.map((d, i) => {
    const sliceAngle = (d.value / total) * 2 * Math.PI;
    const endAngle = startAngle + sliceAngle;
    const largeArc = sliceAngle > Math.PI ? 1 : 0;

    const x1Outer = cx + outerR * Math.cos(startAngle);
    const y1Outer = cy + outerR * Math.sin(startAngle);
    const x2Outer = cx + outerR * Math.cos(endAngle);
    const y2Outer = cy + outerR * Math.sin(endAngle);

    let path: string;
    if (innerR > 0) {
      const x1Inner = cx + innerR * Math.cos(endAngle);
      const y1Inner = cy + innerR * Math.sin(endAngle);
      const x2Inner = cx + innerR * Math.cos(startAngle);
      const y2Inner = cy + innerR * Math.sin(startAngle);
      path = [
        `M ${x1Outer} ${y1Outer}`,
        `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2Outer} ${y2Outer}`,
        `L ${x1Inner} ${y1Inner}`,
        `A ${innerR} ${innerR} 0 ${largeArc} 0 ${x2Inner} ${y2Inner}`,
        'Z',
      ].join(' ');
    } else {
      path = [
        `M ${cx} ${cy}`,
        `L ${x1Outer} ${y1Outer}`,
        `A ${outerR} ${outerR} 0 ${largeArc} 1 ${x2Outer} ${y2Outer}`,
        'Z',
      ].join(' ');
    }

    // Label position
    const midAngle = startAngle + sliceAngle / 2;
    const labelR = outerR * 0.65;
    const labelX = cx + labelR * Math.cos(midAngle);
    const labelY = cy + labelR * Math.sin(midAngle);
    const pct = ((d.value / total) * 100).toFixed(0);

    startAngle = endAngle;

    return {
      path,
      color: colors[i % colors.length],
      datum: d,
      labelX,
      labelY,
      pct,
      sliceAngle,
    };
  });

  return (
    <div ref={containerRef} className={`relative flex justify-center ${className || ''}`} style={{ height }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {arcs.map((arc, i) => (
          <g key={i}>
            <path
              d={arc.path}
              fill={arc.color}
              fillOpacity={0.85}
              stroke="#0a0e1a"
              strokeWidth={1.5}
              onMouseEnter={(e) => handleMouseEnter(arc.datum, e)}
              onMouseMove={(e) => handleMouseMove(arc.datum, e)}
              onMouseLeave={() => setTooltip(null)}
              className="cursor-pointer transition-opacity hover:opacity-100"
            />
            {showLabels && arc.sliceAngle > 0.3 && (
              <text
                x={arc.labelX}
                y={arc.labelY}
                textAnchor="middle"
                dominantBaseline="central"
                fill="#e5e7eb"
                fontSize={9}
                fontFamily="monospace"
              >
                {arc.datum.name} {arc.pct}%
              </text>
            )}
          </g>
        ))}
      </svg>
      {tooltip && (
        <div
          className="absolute pointer-events-none z-50 px-2 py-1 rounded text-xs font-mono bg-[#1f2937] border border-[#374151] text-gray-200 whitespace-nowrap"
          style={{ left: tooltip.x, top: tooltip.y, transform: 'translate(-50%, -100%)' }}
        >
          {tooltip.name}: {tooltip.value}
        </div>
      )}
    </div>
  );
};
