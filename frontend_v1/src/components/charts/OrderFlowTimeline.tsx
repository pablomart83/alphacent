import { type FC, useMemo } from 'react';
import { format, subDays } from 'date-fns';
import { colors } from '../../lib/design-tokens';

export interface OrderEvent {
  id: string;
  symbol: string;
  status: string; // FILLED, CANCELLED, PENDING, SUBMITTED, REJECTED
  side: string;
  created_at: string;
  quantity: number;
}

export interface OrderFlowTimelineProps {
  orders: OrderEvent[];
  days?: number;
}

const STATUS_COLORS: Record<string, string> = {
  FILLED: colors.green,
  CANCELLED: '#6b7280',
  PENDING: colors.yellow,
  SUBMITTED: colors.blue,
  REJECTED: colors.red,
};

const STATUS_Y: Record<string, number> = {
  FILLED: 3,
  SUBMITTED: 2,
  PENDING: 2,
  CANCELLED: 1,
  REJECTED: 0,
};

const Y_LABELS = ['Rejected', 'Cancelled', 'Pending', 'Filled'];

export const OrderFlowTimeline: FC<OrderFlowTimelineProps> = ({ orders, days = 7 }) => {
  const cutoff = subDays(new Date(), days).getTime();
  const now = Date.now();

  const data = useMemo(() => {
    return orders
      .filter((o) => new Date(o.created_at).getTime() >= cutoff)
      .map((o) => ({
        x: new Date(o.created_at).getTime(),
        y: STATUS_Y[o.status] ?? 2,
        status: o.status,
        symbol: o.symbol,
        side: o.side,
        quantity: o.quantity,
        time: format(new Date(o.created_at), 'MMM dd HH:mm'),
      }));
  }, [orders, cutoff]);

  if (data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-muted-foreground">
        No order events in the last {days} days
      </div>
    );
  }

  // SVG dimensions
  const width = 600;
  const height = 200;
  const padding = { top: 15, right: 20, bottom: 30, left: 75 };
  const plotW = width - padding.left - padding.right;
  const plotH = height - padding.top - padding.bottom;

  // Scales
  const xScale = (t: number) =>
    padding.left + ((t - cutoff) / (now - cutoff)) * plotW;
  const yScale = (y: number) =>
    padding.top + plotH - (y / 3) * plotH;

  // X-axis ticks (evenly spaced dates)
  const tickCount = Math.min(days, 7);
  const xTicks = Array.from({ length: tickCount }, (_, i) => {
    const t = cutoff + ((i + 1) / tickCount) * (now - cutoff);
    return { t, label: format(new Date(t), 'MMM dd') };
  });

  return (
    <div className="min-h-[200px]">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full h-auto"
        style={{ fontFamily: "'JetBrains Mono', 'Courier New', monospace" }}
      >
        {/* Grid lines */}
        {[0, 1, 2, 3].map((y) => (
          <line
            key={`grid-${y}`}
            x1={padding.left}
            x2={width - padding.right}
            y1={yScale(y)}
            y2={yScale(y)}
            stroke="#1f2937"
            strokeDasharray="3 3"
          />
        ))}

        {/* Y-axis labels */}
        {Y_LABELS.map((label, i) => (
          <text
            key={label}
            x={padding.left - 8}
            y={yScale(i) + 3}
            textAnchor="end"
            fill="#9ca3af"
            fontSize={10}
          >
            {label}
          </text>
        ))}

        {/* X-axis ticks */}
        {xTicks.map(({ t, label }) => (
          <text
            key={t}
            x={xScale(t)}
            y={height - 8}
            textAnchor="middle"
            fill="#9ca3af"
            fontSize={10}
          >
            {label}
          </text>
        ))}

        {/* Data points */}
        {data.map((d, i) => (
          <circle
            key={i}
            cx={xScale(d.x)}
            cy={yScale(d.y)}
            r={5}
            fill={STATUS_COLORS[d.status] || '#6b7280'}
            opacity={0.85}
          >
            <title>{`${d.time} — ${d.symbol} ${d.side} ${d.quantity} (${d.status})`}</title>
          </circle>
        ))}
      </svg>
    </div>
  );
};
