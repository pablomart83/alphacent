import { type FC, useMemo } from 'react';
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { chartAxisProps, chartGridProps, chartTooltipStyle, chartTheme, colors } from '../../lib/design-tokens';
import { format, subDays } from 'date-fns';

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

export const OrderFlowTimeline: FC<OrderFlowTimelineProps> = ({ orders, days = 7 }) => {
  const cutoff = subDays(new Date(), days).getTime();

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

  const yLabels = ['Rejected', 'Cancelled', 'Pending', 'Filled'];

  return (
    <div className="min-h-[200px]">
    <ResponsiveContainer width="100%" height={200}>
      <ScatterChart margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
        <CartesianGrid {...chartGridProps} />
        <XAxis
          dataKey="x"
          type="number"
          domain={[cutoff, Date.now()]}
          tickFormatter={(v: number) => format(new Date(v), 'MMM dd')}
          {...chartAxisProps}
        />
        <YAxis
          dataKey="y"
          type="number"
          domain={[-0.5, 3.5]}
          ticks={[0, 1, 2, 3]}
          tickFormatter={(v: number) => yLabels[v] || ''}
          {...chartAxisProps}
          width={70}
        />
        <Tooltip
          contentStyle={{
            ...chartTooltipStyle,
            fontFamily: chartTheme.fontFamily,
            fontSize: 11,
          }}
          formatter={(_: unknown, __: unknown, props: any) => {
            const p = props.payload;
            return [`${p.symbol} ${p.side} ${p.quantity}`, p.status];
          }}
          labelFormatter={(v: unknown) => format(new Date(Number(v)), 'MMM dd HH:mm')}
        />
        <Scatter data={data} shape="circle">
          {data.map((entry, idx) => (
            <Cell key={idx} fill={STATUS_COLORS[entry.status] || '#6b7280'} r={5} />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
    </div>
  );
};
