/**
 * Chart utility functions extracted from InteractiveChart.
 * These are pure date-filtering helpers with no Recharts dependency.
 */
import { subWeeks, subMonths, subYears, parseISO, isAfter } from 'date-fns';

/**
 * Compute the start-date cutoff for a given period string relative to an
 * anchor date (typically the last data point).
 */
export function periodStartDate(period: string, anchor: Date): Date | null {
  switch (period) {
    case '1W':
      return subWeeks(anchor, 1);
    case '1M':
      return subMonths(anchor, 1);
    case '3M':
      return subMonths(anchor, 3);
    case '6M':
      return subMonths(anchor, 6);
    case '1Y':
      return subYears(anchor, 1);
    case 'ALL':
    default:
      return null; // no filtering
  }
}

/**
 * Filter data array by period. Returns the full array when period is ALL or
 * when the data has no parseable dates.
 */
export function filterDataByPeriod<T extends Record<string, unknown>>(
  data: T[],
  xAxisKey: string,
  period: string,
): T[] {
  if (period === 'ALL' || data.length === 0) return data;

  const lastDateStr = String(data[data.length - 1][xAxisKey]);
  const anchor = parseISO(lastDateStr);
  if (isNaN(anchor.getTime())) return data;

  const start = periodStartDate(period, anchor);
  if (!start) return data;

  return data.filter((d) => {
    const dateStr = String(d[xAxisKey]);
    const date = parseISO(dateStr);
    return !isNaN(date.getTime()) && isAfter(date, start);
  });
}
