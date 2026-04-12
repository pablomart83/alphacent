import { type FC, useMemo } from 'react';
import { TvChart, type TvSeriesConfig } from './TvChart';

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

  const series: TvSeriesConfig[] = useMemo(() => [{
    id: 'drawdown',
    type: 'area' as const,
    data: data.map(d => ({
      time: d.date,
      value: d.drawdown_pct,
    })),
    lineColor: '#ef4444',
    topColor: 'rgba(239, 68, 68, 0.4)',
    bottomColor: 'rgba(239, 68, 68, 0.02)',
    lineWidth: 1.5,
  }], [data]);

  return (
    <div className="min-h-[200px]">
      <TvChart series={series} height={height} />
    </div>
  );
};

export type { UnderwaterPlotProps };
