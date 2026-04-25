/**
 * PortfolioEquityChart — Multi-pane quant dashboard chart
 *
 * Architecture:
 *   Single lightweight-charts instance, three panes, one shared time axis.
 *   Crosshair syncs across all panes automatically.
 *
 *   Pane 0 (~55%): Equity curve (area) + SPY benchmark (dashed line) + Realized P&L (dashed green)
 *   Pane 1 (~25%): Daily P&L histogram (green/red bars, zero baseline, Y-axis both sides)
 *   Pane 2 (~20%): Rolling 30d Sharpe (line, zero reference, Y-axis right)
 *
 * Time axis:
 *   - 1d interval: BusinessDay strings "YYYY-MM-DD"
 *   - 4h/1h interval: Unix timestamps (seconds) — timeVisible=true shows HH:MM
 *   - All three panes always use the same format — no mixing
 *
 * Rolling Sharpe:
 *   - Always computed from dailyEquity prop (daily snapshots, never intraday)
 *   - Independent of the interval selector — Sharpe is a daily metric
 *
 * Data flow:
 *   - equityData: intraday or daily equity curve (from analytics endpoint)
 *   - dailyEquity: always daily equity curve (from dashboard endpoint)
 *   - spyData: daily SPY closes (scaled to portfolio start equity)
 *   - period: client-side filter (no re-fetch)
 *   - interval: triggers parent re-fetch, controls time format
 */

import { type FC, useEffect, useRef, useMemo } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  AreaSeries,
  LineSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type Time,
} from 'lightweight-charts';
import { cn } from '../../lib/utils';
import { filterDataByPeriod } from '../../lib/chart-utils';

// ── Types ─────────────────────────────────────────────────────────────────

export interface EquityDataPoint {
  date: string; // "YYYY-MM-DD", "YYYY-MM-DD HH:MM", or Unix timestamp string
  equity: number;
  realized?: number | null;
}

export interface SpyDataPoint {
  date: string;
  close: number;
}

export interface PortfolioEquityChartProps {
  equityData: EquityDataPoint[];       // interval-aware equity curve
  dailyEquity: EquityDataPoint[];      // always daily — for Rolling Sharpe
  spyData?: SpyDataPoint[];
  period: string;
  onPeriodChange: (p: string) => void;
  interval?: '1d' | '4h' | '1h';
  onIntervalChange?: (iv: '1d' | '4h' | '1h') => void;
  height?: number;
}

// ── Constants ─────────────────────────────────────────────────────────────

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'] as const;

const THEME = {
  bg:        '#0a0e1a',
  grid:      '#1a2035',
  text:      '#6b7280',
  crosshair: '#374151',
  portfolio: '#3b82f6',
  spy:       '#6b7280',
  realized:  '#22c55e',
  pnlPos:    'rgba(34,197,94,0.75)',
  pnlNeg:    'rgba(239,68,68,0.75)',
  zero:      '#374151',
  sharpe:    '#a78bfa',
  border:    '#1a2035',
};

// ── Helpers ───────────────────────────────────────────────────────────────

function toTime(s: string): Time {
  if (/^\d{9,11}$/.test(s)) return parseInt(s, 10) as Time;
  if (s.length > 10 && s[10] === ' ') {
    const dt = new Date(s.replace(' ', 'T') + ':00Z');
    if (!isNaN(dt.getTime())) return Math.floor(dt.getTime() / 1000) as Time;
  }
  return s.slice(0, 10) as Time;
}

function toDayKey(raw: string): string {
  if (/^\d{9,11}$/.test(raw)) return new Date(parseInt(raw, 10) * 1000).toISOString().slice(0, 10);
  return raw.slice(0, 10);
}

function fmtDollar(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

function fmtPnl(v: number): string {
  const sign = v >= 0 ? '+' : '';
  if (Math.abs(v) >= 1_000) return `${sign}$${(v / 1_000).toFixed(1)}K`;
  return `${sign}$${v.toFixed(0)}`;
}

// ── Rolling Sharpe computation (always daily) ─────────────────────────────

function computeRollingSharpe(
  daily: EquityDataPoint[],
  window = 30,
): Array<{ time: Time; value: number }> {
  // Strictly daily: reject anything that isn't YYYY-MM-DD
  const pts = daily.filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d.date));
  if (pts.length < window + 2) return [];
  const returns: number[] = [];
  for (let i = 1; i < pts.length; i++) {
    const prev = pts[i - 1].equity;
    const curr = pts[i].equity;
    returns.push(prev > 0 ? (curr - prev) / prev : 0);
  }
  const result: Array<{ time: Time; value: number }> = [];
  for (let i = window - 1; i < returns.length; i++) {
    const dateIdx = i + 1;
    if (dateIdx >= pts.length) break;
    const slice = returns.slice(i - window + 1, i + 1);
    const mean = slice.reduce((s, v) => s + v, 0) / window;
    const std  = Math.sqrt(slice.reduce((s, v) => s + (v - mean) ** 2, 0) / window) || 1e-9;
    const sharpe = (mean / std) * Math.sqrt(252);
    if (Number.isFinite(sharpe)) {
      result.push({ time: pts[dateIdx].date as Time, value: Math.round(sharpe * 100) / 100 });
    }
  }
  return result;
}

// ── Daily P&L from equity curve ───────────────────────────────────────────

function computeDailyPnl(
  daily: EquityDataPoint[],
): Array<{ time: Time; value: number; color: string }> {
  const pts = daily.filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d.date));
  if (pts.length < 2) return [];
  return pts.slice(1).map((d, i) => {
    const pnl = d.equity - pts[i].equity;
    return {
      time:  d.date as Time,
      value: pnl,
      color: pnl >= 0 ? THEME.pnlPos : THEME.pnlNeg,
    };
  });
}

// ── Main Component ────────────────────────────────────────────────────────

export const PortfolioEquityChart: FC<PortfolioEquityChartProps> = ({
  equityData,
  dailyEquity,
  spyData,
  period,
  onPeriodChange,
  interval = '1d',
  onIntervalChange,
  height = 560,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const seriesRef    = useRef<Record<string, ISeriesApi<SeriesType>>>({});
  const roRef        = useRef<ResizeObserver | null>(null);

  // ── Filter equity curve by period ─────────────────────────────────────
  const filtered = useMemo(() => {
    if (!equityData?.length) return [];
    return filterDataByPeriod(equityData.map(d => ({ ...d })), 'date', period) as EquityDataPoint[];
  }, [equityData, period]);

  // ── Filter daily equity by period (for P&L and Sharpe panes) ──────────
  const filteredDaily = useMemo(() => {
    if (!dailyEquity?.length) return [];
    return filterDataByPeriod(
      dailyEquity.filter(d => /^\d{4}-\d{2}-\d{2}$/.test(d.date)).map(d => ({ ...d })),
      'date',
      period,
    ) as EquityDataPoint[];
  }, [dailyEquity, period]);

  // ── Derive all series data ─────────────────────────────────────────────
  const chartData = useMemo(() => {
    if (filtered.length < 2) return null;

    const startEquity = filtered[0].equity;
    const lastEquity  = filtered[filtered.length - 1].equity;
    const totalReturn = ((lastEquity - startEquity) / startEquity) * 100;

    // Pane 0: portfolio area
    const portfolio = filtered.map(d => ({ time: toTime(d.date), value: d.equity }));

    // Pane 0: realized P&L line
    let realized: Array<{ time: Time; value: number }> | null = null;
    if (filtered.some(d => d.realized != null)) {
      const startR = filtered[0].realized ?? 0;
      const pts = filtered
        .filter(d => d.realized != null)
        .map(d => ({ time: toTime(d.date), value: startEquity + ((d.realized ?? 0) - startR) }));
      if (pts.length >= 2) realized = pts;
    }

    // Pane 0: SPY benchmark — one point per day, using portfolio's own timestamp for time format
    let spy: Array<{ time: Time; value: number }> | null = null;
    if (spyData?.length) {
      const spyMap = new Map(spyData.map(s => [s.date.slice(0, 10), s.close]));
      const startDay = toDayKey(filtered[0].date);
      const startSpy = spyMap.get(startDay)
        ?? [...spyMap.entries()].find(([d]) => d >= startDay)?.[1];
      if (startSpy && startSpy > 0) {
        const scale = startEquity / startSpy;
        const seen  = new Set<string>();
        const pts = filtered
          .map(d => {
            const day = toDayKey(d.date);
            const v   = spyMap.get(day);
            if (!v || seen.has(day)) return null;
            seen.add(day);
            return { time: toTime(d.date), value: v * scale };
          })
          .filter(Boolean) as Array<{ time: Time; value: number }>;
        if (pts.length >= 2) spy = pts;
      }
    }

    // Pane 1: daily P&L histogram
    const dailyPnl = computeDailyPnl(filteredDaily);

    // Pane 2: rolling 30d Sharpe (always daily, always YYYY-MM-DD)
    const sharpe = computeRollingSharpe(filteredDaily);

    return { portfolio, realized, spy, dailyPnl, sharpe, totalReturn, lastEquity };
  }, [filtered, filteredDaily, spyData]);

  // ── Build / rebuild chart ──────────────────────────────────────────────
  // Key insight: rebuild whenever interval changes (time format changes) or data changes.
  // Period changes are handled by updating series data in-place (no rebuild needed).
  const prevIntervalRef = useRef(interval);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const intervalChanged = prevIntervalRef.current !== interval;
    prevIntervalRef.current = interval;

    // In-place update: period changed but interval and chart structure are the same
    if (chartRef.current && !intervalChanged && seriesRef.current['portfolio']) {
      if (!chartData) return;
      try {
        seriesRef.current['portfolio'].setData(chartData.portfolio as any);
        if (chartData.spy && seriesRef.current['spy'])
          seriesRef.current['spy'].setData(chartData.spy as any);
        if (chartData.realized && seriesRef.current['realized'])
          seriesRef.current['realized'].setData(chartData.realized as any);
        if (seriesRef.current['pnl'])
          seriesRef.current['pnl'].setData(chartData.dailyPnl as any);
        if (seriesRef.current['sharpe'])
          seriesRef.current['sharpe'].setData(chartData.sharpe as any);
        chartRef.current.timeScale().fitContent();
        return;
      } catch {
        // fall through to full rebuild
      }
    }

    // Full rebuild
    roRef.current?.disconnect();
    chartRef.current?.remove();
    chartRef.current = null;
    seriesRef.current = {};
    el.innerHTML = '';

    if (!chartData) return;

    const TOOLBAR_H = 32;
    const chartH    = height - TOOLBAR_H;

    // Pane height distribution: 55% equity, 25% P&L, 20% Sharpe
    const pane0H = Math.round(chartH * 0.55);
    const pane1H = Math.round(chartH * 0.25);
    const pane2H = chartH - pane0H - pane1H;

    const chart = createChart(el, {
      width:  el.clientWidth,
      height: chartH,
      layout: {
        background:  { type: ColorType.Solid, color: THEME.bg },
        textColor:   THEME.text,
        fontFamily:  "'JetBrains Mono', 'Courier New', monospace",
        fontSize:    11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: THEME.grid, style: LineStyle.Dotted },
        horzLines: { color: THEME.grid, style: LineStyle.Dotted },
      },
      crosshair: {
        mode:     CrosshairMode.Normal,
        vertLine: { color: THEME.crosshair, labelBackgroundColor: '#1f2937' },
        horzLine: { color: THEME.crosshair, labelBackgroundColor: '#1f2937' },
      },
      timeScale: {
        borderColor:  THEME.border,
        timeVisible:  interval !== '1d',
        secondsVisible: false,
        rightOffset:  6,
        barSpacing:   interval === '1h' ? 4 : interval === '4h' ? 6 : 8,
        fixLeftEdge:  true,
        fixRightEdge: true,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale:  { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // ── Pane 0: Equity curve ───────────────────────────────────────────
    const pane0 = chart.panes()[0];
    pane0.setHeight(pane0H);

    if (chartData.spy) {
      const s = chart.addSeries(LineSeries, {
        color:            THEME.spy,
        lineWidth:        1,
        lineStyle:        LineStyle.Dashed,
        priceScaleId:     'left',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
      }, 0);
      s.setData(chartData.spy);
      seriesRef.current['spy'] = s;
    }

    if (chartData.realized) {
      const s = chart.addSeries(LineSeries, {
        color:            THEME.realized,
        lineWidth:        1,
        lineStyle:        LineStyle.Dashed,
        priceScaleId:     'left',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
      }, 0);
      s.setData(chartData.realized);
      seriesRef.current['realized'] = s;
    }

    const portfolio = chart.addSeries(AreaSeries, {
      lineColor:        THEME.portfolio,
      topColor:         'rgba(59,130,246,0.15)',
      bottomColor:      'rgba(59,130,246,0.01)',
      lineWidth:        2,
      priceScaleId:     'left',
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
    }, 0);
    portfolio.setData(chartData.portfolio);
    seriesRef.current['portfolio'] = portfolio;

    chart.priceScale('left', 0).applyOptions({
      visible:      true,
      borderColor:  THEME.border,
      scaleMargins: { top: 0.06, bottom: 0.04 },
    });
    chart.priceScale('right', 0).applyOptions({ visible: false });

    // ── Pane 1: Daily P&L ─────────────────────────────────────────────
    if (chartData.dailyPnl.length >= 2) {
      const pane1 = chart.addPane();
      pane1.setHeight(pane1H);

      // Zero baseline
      const zero = chart.addSeries(LineSeries, {
        color:            THEME.zero,
        lineWidth:        1,
        lineStyle:        LineStyle.Solid,
        priceScaleId:     'right',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: () => '', minMove: 1 },
      }, 1);
      zero.setData([
        { time: chartData.dailyPnl[0].time,                          value: 0 },
        { time: chartData.dailyPnl[chartData.dailyPnl.length - 1].time, value: 0 },
      ]);

      const pnl = chart.addSeries(HistogramSeries, {
        priceScaleId:     'right',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtPnl, minMove: 1 },
      }, 1);
      pnl.setData(chartData.dailyPnl);
      seriesRef.current['pnl'] = pnl;

      chart.priceScale('right', 1).applyOptions({
        visible:      true,
        borderColor:  THEME.border,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      });
      chart.priceScale('left', 1).applyOptions({ visible: false });
    }

    // ── Pane 2: Rolling 30d Sharpe ────────────────────────────────────
    if (chartData.sharpe.length >= 2) {
      const pane2 = chart.addPane();
      pane2.setHeight(pane2H);

      // Zero reference line
      const zeroS = chart.addSeries(LineSeries, {
        color:            THEME.zero,
        lineWidth:        1,
        lineStyle:        LineStyle.Dotted,
        priceScaleId:     'right',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: () => '', minMove: 0.01 },
      }, 2);
      zeroS.setData([
        { time: chartData.sharpe[0].time,                        value: 0 },
        { time: chartData.sharpe[chartData.sharpe.length - 1].time, value: 0 },
      ]);

      const sharpe = chart.addSeries(LineSeries, {
        color:            THEME.sharpe,
        lineWidth:        2,
        priceScaleId:     'right',
        lastValueVisible: true,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: (v: number) => v.toFixed(2), minMove: 0.01 },
      }, 2);
      sharpe.setData(chartData.sharpe);
      seriesRef.current['sharpe'] = sharpe;

      chart.priceScale('right', 2).applyOptions({
        visible:      true,
        borderColor:  THEME.border,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      });
      chart.priceScale('left', 2).applyOptions({ visible: false });
    }

    chart.timeScale().fitContent();

    // ── ResizeObserver ─────────────────────────────────────────────────
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const w = Math.round(e.contentRect.width);
        if (w > 0 && chartRef.current) chartRef.current.applyOptions({ width: w });
      }
    });
    ro.observe(el);
    roRef.current = ro;

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = {};
    };
  }, [chartData, interval, height]);

  // ── Render ─────────────────────────────────────────────────────────────
  const totalReturn = chartData?.totalReturn ?? null;
  const hasSpy      = !!chartData?.spy;
  const hasRealized = !!chartData?.realized;

  return (
    <div className="w-full flex flex-col">
      {/* Toolbar */}
      <div className="flex items-center justify-between px-0.5 mb-1 h-[28px] shrink-0">
        <div className="flex items-center gap-1.5">
          <div className="flex items-center gap-px">
            {PERIODS.map(p => (
              <button
                key={p}
                onClick={() => onPeriodChange(p)}
                className={cn(
                  'px-2 py-0.5 text-[10px] font-mono rounded transition-colors',
                  period === p
                    ? 'bg-blue-600/30 text-blue-300 font-semibold'
                    : 'text-gray-600 hover:text-gray-300',
                )}
              >
                {p}
              </button>
            ))}
          </div>
          {onIntervalChange && (
            <>
              <span className="text-gray-800 text-[10px]">|</span>
              <div className="flex items-center gap-px">
                {(['1d', '4h', '1h'] as const).map(iv => (
                  <button
                    key={iv}
                    onClick={() => onIntervalChange(iv)}
                    className={cn(
                      'px-2 py-0.5 text-[10px] font-mono rounded transition-colors',
                      interval === iv
                        ? 'bg-gray-700 text-gray-200 font-semibold'
                        : 'text-gray-600 hover:text-gray-300',
                    )}
                  >
                    {iv.toUpperCase()}
                  </button>
                ))}
              </div>
            </>
          )}
        </div>

        {/* Stats + legend */}
        <div className="flex items-center gap-3 text-[10px] font-mono">
          {totalReturn != null && (
            <span className={cn('font-semibold', totalReturn >= 0 ? 'text-green-400' : 'text-red-400')}>
              {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
            </span>
          )}
          <span className="flex items-center gap-1 text-gray-600">
            <span className="w-3 h-[2px] bg-blue-500 inline-block rounded" /> Equity
          </span>
          {hasRealized && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 inline-block" style={{ borderTop: '1.5px dashed #22c55e' }} /> Realized
            </span>
          )}
          {hasSpy && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 inline-block" style={{ borderTop: '1.5px dashed #6b7280' }} /> SPY
            </span>
          )}
          <span className="flex items-center gap-1 text-gray-600">
            <span className="w-3 h-[2px] bg-violet-400/60 inline-block rounded" /> Sharpe
          </span>
        </div>
      </div>

      {/* Pane labels (left side, absolute positioned) */}
      {chartData && (
        <div className="relative" style={{ height: height - 32 }}>
          <div ref={containerRef} style={{ width: '100%', height: '100%' }} />
          {/* Pane labels */}
          <div className="absolute left-1 top-1 text-[9px] font-mono text-gray-600 pointer-events-none select-none">
            Equity
          </div>
          {chartData.dailyPnl.length >= 2 && (
            <div
              className="absolute left-1 text-[9px] font-mono text-gray-600 pointer-events-none select-none"
              style={{ top: `${Math.round((height - 32) * 0.55) + 2}px` }}
            >
              Daily P&L
            </div>
          )}
          {chartData.sharpe.length >= 2 && (
            <div
              className="absolute left-1 text-[9px] font-mono text-gray-600 pointer-events-none select-none"
              style={{ top: `${Math.round((height - 32) * 0.80) + 2}px` }}
            >
              Sharpe 30d
            </div>
          )}
        </div>
      )}

      {!chartData && (
        <div
          className="flex items-center justify-center text-gray-700 text-xs font-mono"
          style={{ height: height - 32 }}
        >
          No data
        </div>
      )}
    </div>
  );
};
