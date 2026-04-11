import { type FC } from 'react';
import {
  ComposedChart,
  Line,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { chartAxisProps, chartGridProps, chartTooltipStyle, chartTheme, colors } from '../../lib/design-tokens';
import { formatCurrency } from '../../lib/utils';

export interface PricePoint {
  date: string;
  price: number;
}

export interface OrderAnnotation {
  date: string;
  price: number;
  side: 'BUY' | 'SELL';
  quantity?: number;
}

export interface AssetPlotProps {
  priceData: PricePoint[];
  orders?: OrderAnnotation[];
  symbol: string;
  height?: number;
}

export const AssetPlot: FC<AssetPlotProps> = ({ priceData, orders = [], symbol, height = 300 }) => {
  // Merge orders into the price data timeline for scatter overlay
  const buyOrders = orders
    .filter((o) => o.side === 'BUY')
    .map((o) => ({ date: o.date, buyPrice: o.price, quantity: o.quantity }));

  const sellOrders = orders
    .filter((o) => o.side === 'SELL')
    .map((o) => ({ date: o.date, sellPrice: o.price, quantity: o.quantity }));

  if (priceData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ height }}>
        No price data available for {symbol}
      </div>
    );
  }

  return (
    <div className="min-h-[200px]">
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={priceData} margin={{ top: 10, right: 20, bottom: 10, left: 10 }}>
        <CartesianGrid {...chartGridProps} />
        <XAxis
          dataKey="date"
          {...chartAxisProps}
          tickFormatter={(v: string) => {
            const d = new Date(v);
            return `${d.getMonth() + 1}/${d.getDate()}`;
          }}
        />
        <YAxis
          {...chartAxisProps}
          domain={['auto', 'auto']}
          tickFormatter={(v: number) => `$${v.toFixed(0)}`}
        />
        <Tooltip
          contentStyle={{
            ...chartTooltipStyle,
            fontFamily: chartTheme.fontFamily,
            fontSize: 11,
          }}
          formatter={((value: number | undefined, name: string | undefined) => {
            const v = value ?? 0;
            if (name === 'price') return [formatCurrency(v), 'Price'];
            if (name === 'buyPrice') return [formatCurrency(v), 'Buy ↑'];
            if (name === 'sellPrice') return [formatCurrency(v), 'Sell ↓'];
            return [String(v), name ?? ''];
          }) as never}
        />
        <Line
          type="monotone"
          dataKey="price"
          stroke={chartTheme.series.portfolio}
          strokeWidth={1.5}
          dot={false}
          activeDot={{ r: 3 }}
        />
        {/* Buy annotations */}
        {buyOrders.length > 0 && (
          <Scatter data={buyOrders} dataKey="buyPrice" shape="triangle" fill={colors.green}>
            {buyOrders.map((_, idx) => (
              <Cell key={idx} fill={colors.green} />
            ))}
          </Scatter>
        )}
        {/* Sell annotations */}
        {sellOrders.length > 0 && (
          <Scatter data={sellOrders} dataKey="sellPrice" shape="triangle" fill={colors.red}>
            {sellOrders.map((_, idx) => (
              <Cell key={idx} fill={colors.red} />
            ))}
          </Scatter>
        )}
      </ComposedChart>
    </ResponsiveContainer>
    </div>
  );
};
