import { type FC } from 'react';
import {
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ComposedChart,
  ReferenceLine,
} from 'recharts';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
} from '../../lib/design-tokens';

interface UnderwaterPlotProps {
  data: Array<{ date: string; drawdown_pct: number }>;
  height?: number;
}

export const UnderwaterPlot: FC<UnderwaterPlotProps> = ({ data, height = 300 }) => {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground font-mono text-sm">
        No drawdown data available
      </div>
    );
  }

  return (
    <div className="min-h-[200px]">
    <ResponsiveContainer width="100%" height={height}>
      <ComposedChart data={data}>
        <CartesianGrid {...chartGridProps} />
        <XAxis dataKey="date" {...chartAxisProps} />
        <YAxis
          {...chartAxisProps}
          tickFormatter={(v: number) => `${v.toFixed(0)}%`}
        />
        <Tooltip
          contentStyle={{
            ...chartTooltipStyle,
            fontFamily: chartTheme.fontFamily,
            fontSize: 11,
          }}
          cursor={{ stroke: '#9ca3af', strokeDasharray: '3 3' }}
          formatter={(value: number | undefined) => [`${(value ?? 0).toFixed(2)}%`, 'Drawdown']}
          labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
        />
        <ReferenceLine y={0} stroke={chartTheme.grid} strokeDasharray="3 3" />
        <Area
          type="monotone"
          dataKey="drawdown_pct"
          stroke="#ef4444"
          fill="#ef4444"
          fillOpacity={0.4}
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
    </div>
  );
};

export type { UnderwaterPlotProps };
