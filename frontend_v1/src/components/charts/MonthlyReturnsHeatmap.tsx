import { type FC, useMemo } from 'react';
import { cn } from '../../lib/utils';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '../ui/tooltip';

interface MonthlyReturnEntry {
  year: number;
  month: number;
  return_pct: number;
}

interface MonthlyReturnsHeatmapProps {
  data: MonthlyReturnEntry[];
}

const MONTH_LABELS = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

/**
 * Map a return percentage to a background color using a diverging scale.
 * Negative → red, zero → neutral gray, positive → green.
 */
function returnToColor(value: number): string {
  if (value > 5) return 'bg-green-500/80';
  if (value > 3) return 'bg-green-500/60';
  if (value > 1) return 'bg-green-500/40';
  if (value > 0) return 'bg-green-500/20';
  if (value === 0) return 'bg-gray-700/40';
  if (value > -1) return 'bg-red-500/20';
  if (value > -3) return 'bg-red-500/40';
  if (value > -5) return 'bg-red-500/60';
  return 'bg-red-500/80';
}

export const MonthlyReturnsHeatmap: FC<MonthlyReturnsHeatmapProps> = ({ data }) => {
  const { years, grid } = useMemo(() => {
    if (!data || data.length === 0) return { years: [] as number[], grid: new Map<string, number>() };

    const grid = new Map<string, number>();
    const yearSet = new Set<number>();

    for (const entry of data) {
      yearSet.add(entry.year);
      grid.set(`${entry.year}-${entry.month}`, entry.return_pct);
    }

    const years = Array.from(yearSet).sort((a, b) => a - b);
    return { years, grid };
  }, [data]);

  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-muted-foreground font-mono text-sm">
        No monthly returns data available
      </div>
    );
  }

  return (
    <TooltipProvider>
      <div className="overflow-x-auto">
        <table className="border-collapse">
          <thead>
            <tr>
              <th className="px-2 py-1 text-xs font-mono text-muted-foreground text-left">Year</th>
              {MONTH_LABELS.map((m) => (
                <th key={m} className="px-2 py-1 text-xs font-mono text-muted-foreground text-center w-14">
                  {m}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {years.map((year) => (
              <tr key={year}>
                <td className="px-2 py-1 text-xs font-mono text-muted-foreground font-semibold">
                  {year}
                </td>
                {Array.from({ length: 12 }, (_, i) => i + 1).map((month) => {
                  const key = `${year}-${month}`;
                  const value = grid.get(key);
                  const hasValue = value !== undefined;

                  return (
                    <td key={key} className="px-0.5 py-0.5">
                      {hasValue ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <div
                              className={cn(
                                'w-14 h-8 rounded-sm flex items-center justify-center cursor-default transition-colors',
                                returnToColor(value),
                              )}
                            >
                              <span className="text-xs font-mono font-medium text-white/90">
                                {value >= 0 ? '+' : ''}{value.toFixed(1)}%
                              </span>
                            </div>
                          </TooltipTrigger>
                          <TooltipContent>
                            <div className="font-mono text-xs space-y-0.5">
                              <p className="font-semibold">{MONTH_LABELS[month - 1]} {year}</p>
                              <p>Return: {value >= 0 ? '+' : ''}{value.toFixed(2)}%</p>
                            </div>
                          </TooltipContent>
                        </Tooltip>
                      ) : (
                        <div className="w-14 h-8 rounded-sm bg-gray-800/30 flex items-center justify-center">
                          <span className="text-xs font-mono text-muted-foreground/40">—</span>
                        </div>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </TooltipProvider>
  );
};

export type { MonthlyReturnsHeatmapProps, MonthlyReturnEntry };
