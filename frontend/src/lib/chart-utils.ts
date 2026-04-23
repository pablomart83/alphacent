/**
 * Chart utility functions extracted from InteractiveChart.
 * These are pure date-filtering helpers with no Recharts dependency.
 */
import { subWeeks, subMonths, subYears, parseISO, isAfter } from 'date-fns';
import type { TvSeriesConfig } from '../components/charts/TvChart';
import { chartTheme } from './design-tokens';

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

// ── Equity curve helpers ───────────────────────────────────────────────────

export function normalizeToBase100(
  data: Array<{ date: string; value: number }>,
): Array<{ date: string; value: number }> {
  if (data.length === 0) return [];
  const base = data[0].value;
  if (base === 0) return data;
  return data.map((d) => ({ date: d.date, value: (d.value / base) * 100 }));
}

export function computeDrawdown(
  data: Array<{ date: string; value: number }>,
): Array<{ date: string; drawdown: number }> {
  if (data.length === 0) return [];
  let peak = -Infinity;
  return data.map((d) => {
    if (d.value > peak) peak = d.value;
    const dd = peak > 0 ? ((d.value - peak) / peak) * 100 : 0;
    return { date: d.date, drawdown: dd };
  });
}

export interface EquityCurveSeries {
  mainSeries: TvSeriesConfig[];
  drawdownSeries: TvSeriesConfig[];
  hasSpy: boolean;
  hasRealized: boolean;
}

export function buildEquityCurveSeries(
  equityData: Array<{ date: string; equity: number }>,
  spyData: Array<{ date: string; close: number }> | undefined,
  period: string,
  realizedData?: Array<{ date: string; realized: number }>,
  trades?: Array<{ date: string; pnl: number; symbol?: string }>,
): EquityCurveSeries {
  const filteredEquity = filterDataByPeriod(
    equityData.map((d) => ({ ...d })),
    'date',
    period,
  );

  const normPortfolio = normalizeToBase100(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );

  const hasSpy = !!spyData && spyData.length > 0;
  const normSpyMap = new Map<string, number>();

  if (hasSpy) {
    const spyMap = new Map<string, number>();
    for (const s of spyData!) spyMap.set(s.date, s.close);
    const alignedSpy: Array<{ date: string; value: number }> = [];
    for (const d of filteredEquity) {
      const v = spyMap.get(d.date);
      if (v !== undefined) alignedSpy.push({ date: d.date, value: v });
    }
    for (const s of normalizeToBase100(alignedSpy)) normSpyMap.set(s.date, s.value);
  }

  const mainSeries: TvSeriesConfig[] = [];

  if (hasSpy) {
    mainSeries.push({
      id: 'alpha',
      type: 'baseline',
      data: normPortfolio
        .filter((d) => normSpyMap.has(d.date))
        .map((d) => ({ time: d.date, value: d.value - (normSpyMap.get(d.date) ?? 0) })),
      baseValue: 0,
      topFillColor1: 'rgba(34,197,94,0.18)',
      topFillColor2: 'rgba(34,197,94,0.02)',
      bottomFillColor1: 'rgba(239,68,68,0.02)',
      bottomFillColor2: 'rgba(239,68,68,0.18)',
      topLineColor: 'transparent',
      bottomLineColor: 'transparent',
      lineWidth: 0,
      priceScaleId: 'alpha',
      lastValueVisible: false,
      priceLineVisible: false,
    });
    mainSeries.push({
      id: 'spy',
      type: 'line',
      data: normPortfolio
        .filter((d) => normSpyMap.has(d.date))
        .map((d) => ({ time: d.date, value: normSpyMap.get(d.date)! })),
      color: chartTheme.series.benchmark,
      lineWidth: 1,
      dashed: true,
      lastValueVisible: false,
      priceLineVisible: false,
    });
  }

  mainSeries.push({
    id: 'portfolio',
    type: 'area',
    data: normPortfolio.map((d) => ({ time: d.date, value: d.value })),
    lineColor: chartTheme.series.portfolio,
    topColor: 'rgba(59,130,246,0.18)',
    bottomColor: 'transparent',
    lineWidth: 2,
    lastValueVisible: false,
    priceLineVisible: false,
  });

  let hasRealized = false;
  if (realizedData && realizedData.length > 0 && filteredEquity.length > 0) {
    const filteredRealized = filterDataByPeriod(
      realizedData.map((d) => ({ date: d.date, value: d.realized })),
      'date',
      period,
    );
    const equityBase = filteredEquity[0]?.equity;
    if (filteredRealized.length > 0 && equityBase && equityBase > 0) {
      hasRealized = true;
      mainSeries.push({
        id: 'realized',
        type: 'line',
        data: filteredRealized.map((d) => ({
          time: d.date,
          value: ((equityBase + d.value) / equityBase) * 100,
        })),
        color: '#22c55e',
        lineWidth: 1,
        dashed: true,
        lastValueVisible: false,
        priceLineVisible: false,
      });
    }
  }

  if (trades && trades.length > 0 && normPortfolio.length > 0) {
    const equityMap = new Map(normPortfolio.map((d) => [d.date, d.value]));
    const filteredTrades = filterDataByPeriod(trades.map((t) => ({ ...t })), 'date', period);
    const markers: Array<{ time: string; value: number; color: string; size: number }> = [];
    for (const trade of filteredTrades) {
      const date = trade.date?.slice(0, 10);
      if (!date) continue;
      const equityVal = equityMap.get(date) ??
        [...equityMap.entries()].filter(([d]) => d <= date).sort(([a], [b]) => b.localeCompare(a))[0]?.[1];
      if (equityVal === undefined) continue;
      markers.push({
        time: date,
        value: equityVal,
        color: trade.pnl >= 0 ? '#22c55e' : '#ef4444',
        size: Math.min(4, Math.max(1, Math.round(Math.abs(trade.pnl) / 125))),
      });
    }
    if (markers.length > 0) {
      const markerSeries: TvSeriesConfig = {
        id: 'trade_markers',
        type: 'line',
        data: markers.map((m) => ({ time: m.time, value: m.value, color: m.color })),
        color: 'transparent',
        lineWidth: 0,
      };
      (markerSeries as any).__tradeMarkers = markers.map((m) => ({
        time: m.time,
        position: 'inBar' as const,
        color: m.color,
        shape: 'circle' as const,
        size: m.size,
        text: '',
      }));
      mainSeries.push(markerSeries);
    }
  }

  const drawdownRaw = computeDrawdown(
    filteredEquity.map((d) => ({ date: d.date, value: d.equity })),
  );
  const drawdownSeries: TvSeriesConfig[] = [{
    id: 'drawdown',
    type: 'area',
    data: drawdownRaw.map((d) => ({ time: d.date, value: d.drawdown })),
    lineColor: chartTheme.series.drawdown,
    topColor: 'rgba(239,68,68,0.4)',
    bottomColor: 'rgba(239,68,68,0.05)',
    lineWidth: 1,
    lastValueVisible: false,
    priceLineVisible: false,
  }];

  return { mainSeries, drawdownSeries, hasSpy, hasRealized };
}
