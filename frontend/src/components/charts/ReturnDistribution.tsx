import { type FC, useMemo } from 'react';
import {
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Line,
  ComposedChart,
  Bar,
} from 'recharts';
import { Badge } from '../ui/Badge';
import {
  chartAxisProps,
  chartGridProps,
  chartTooltipStyle,
  chartTheme,
} from '../../lib/design-tokens';

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

  // Compute mean and std from bin midpoints weighted by count
  const totalCount = data.reduce((s, d) => s + d.count, 0);
  if (totalCount === 0) return data.map((d) => ({ ...d, normal: 0 }));

  const mean = data.reduce((s, d) => s + d.bin * d.count, 0) / totalCount;
  const variance =
    data.reduce((s, d) => s + d.count * (d.bin - mean) ** 2, 0) / totalCount;
  const std = Math.sqrt(variance) || 1;

  // Bin width (assume uniform spacing)
  const binWidth =
    data.length > 1 ? Math.abs(data[1].bin - data[0].bin) : 1;

  return data.map((d) => {
    const z = (d.bin - mean) / std;
    const pdf = (1 / (std * Math.sqrt(2 * Math.PI))) * Math.exp(-0.5 * z * z);
    const normal = pdf * totalCount * binWidth;
    return { ...d, normal: Math.round(normal * 100) / 100 };
  });
}

export const ReturnDistribution: FC<ReturnDistributionProps> = ({
  data,
  skew,
  kurtosis,
  height = 300,
}) => {
  const chartData = useMemo(() => computeNormalOverlay(data), [data]);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground font-mono text-sm">
        No return distribution data available
      </div>
    );
  }

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
      <div className="min-h-[200px]">
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={chartData}>
          <CartesianGrid {...chartGridProps} />
          <XAxis
            dataKey="bin"
            {...chartAxisProps}
            tickFormatter={(v: number) => `${v.toFixed(1)}%`}
          />
          <YAxis {...chartAxisProps} />
          <Tooltip
            contentStyle={{
              ...chartTooltipStyle,
              fontFamily: chartTheme.fontFamily,
              fontSize: 11,
            }}
            cursor={{ fill: 'rgba(59,130,246,0.1)' }}
            formatter={((value: number | undefined, name: string) => [
              name === 'normal' ? (value ?? 0).toFixed(1) : String(value ?? 0),
              name === 'normal' ? 'Normal Dist.' : 'Count',
            ]) as never}
            labelFormatter={((label: unknown) => `Return: ${Number(label).toFixed(2)}%`) as never}
            labelStyle={{ color: '#f3f4f6', marginBottom: 4 }}
          />
          <Bar
            dataKey="count"
            fill="#3b82f6"
            fillOpacity={0.7}
            radius={[2, 2, 0, 0]}
          />
          <Line
            type="monotone"
            dataKey="normal"
            stroke="#eab308"
            strokeWidth={2}
            dot={false}
            strokeDasharray="4 2"
          />
        </ComposedChart>
      </ResponsiveContainer>
      </div>
    </div>
  );
};

export type { ReturnDistributionProps };
