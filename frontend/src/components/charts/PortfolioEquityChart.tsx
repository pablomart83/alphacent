/**
 * PortfolioEquityChart — Multi-pane equity curve for AlphaCent.
 *
 * Architecture (quant-first, lightweight-charts v5):
 *
 *  Single createChart instance with THREE panes sharing one time axis:
 *    Pane 0 (~55%): Portfolio equity area + SPY benchmark line + Realized P&L line
 *    Pane 1 (~25%): Daily P&L histogram  (always daily data regardless of interval)
 *    Pane 2 (~20%): Rolling 30d Sharpe   (always daily data regardless of interval)
 *
 *  Time format rule — decided once from interval, applied to ALL series:
 *    1d  → BusinessDay string "YYYY-MM-DD"
 *    4h/1h → Unix integer (seconds since epoch)
 *
 *  Daily P&L and Rolling Sharpe always use daily equity snapshots (dailyEquity prop).
 *  When interval is 4h/1h those daily dates are converted to Unix so they match
 *  the time format used by the equity curve — lightweight-charts requires all series
 *  on the same chart to use the same Time type.
 *
 *  Update paths:
 *    Period change  → client-side filter → series.setData() in-place (no chart rebuild)
 *    Interval change → time format changes → full chart teardown + rebuild
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
  /** "YYYY-MM-DD" (daily) or Unix timestamp string (intraday) */
  date: string;
  equity: number;
  realized?: number | null;
}

export interface SpyDataPoint {
  date: string; // always "YYYY-MM-DD"
  close: number;
}

export interface PortfolioEquityChartProps {
  equityData: EquityDataPoint[];
  /** Daily equity snapshots — used for P&L histogram and Rolling Sharpe.
   *  Always daily regardless of the selected interval. */
  dailyEquity?: EquityDataPoint[];
  spyData?: SpyDataPoint[];
  period: string;
  onPeriodChange: (p: string) => void;
  interval?: '1d' | '4h' | '1h';
  onIntervalChange?: (iv: '1d' | '4h' | '1h') => void;
  height?: number;
}

// ── Constants ─────────────────────────────────────────────────────────────

const PERIODS = ['1W', '1M', '3M', '6M', '1Y', 'ALL'] as const;

const PANE_HEIGHTS = { equity: 0.55, pnl: 0.25, sharpe: 0.20 };

const THEME = {
  bg:           '#0a0e1a',
  grid:         '#1a2035',
  text:         '#6b7280',
  crosshair:    '#374151',
  portfolio:    '#3b82f6',
  spy:          '#6b7280',
  realized:     '#22c55e',
  pnlPos:       'rgba(34,197,94,0.75)',
  pnlNeg:       'rgba(239,68,68,0.75)',
  sharpe:       '#a78bfa',
  sharpeZero:   '#374151',
};

// ── Time helpers ──────────────────────────────────────────────────────────

/** Convert any date string to a lightweight-charts Time value.
 *  The isIntraday flag determines the format for the entire chart instance —
 *  all series must use the same type. */
function toTime(s: string, isIntraday: boolean): Time {
  // Unix timestamp string (9-11 all-digit chars) — always convert to integer
  if (/^\d{9,11}$/.test(s)) {
    const unix = parseInt(s, 10);
    if (isIntraday) return unix as Time;
    // Daily mode but received a Unix string — convert to "YYYY-MM-DD"
    return new Date(unix * 1000).toISOString().slice(0, 10) as Time;
  }

  if (isIntraday) {
    // "YYYY-MM-DD HH:MM" → UTC Unix
    if (s.length > 10 && s[10] === ' ') {
      const dt = new Date(s.replace(' ', 'T') + ':00Z');
      if (!isNaN(dt.getTime())) return Math.floor(dt.getTime() / 1000) as Time;
    }
    // "YYYY-MM-DD" daily date in intraday mode → midnight UTC Unix
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) {
      return Math.floor(new Date(s + 'T00:00:00Z').getTime() / 1000) as Time;
    }
    // Fallback
    const n = parseInt(s, 10);
    if (!isNaN(n)) return n as Time;
    return Math.floor(new Date(s).getTime() / 1000) as Time;
  } else {
    // Daily mode — BusinessDay string "YYYY-MM-DD"
    return s.slice(0, 10) as Time;
  }
}

/** Extract "YYYY-MM-DD" from any date string (for SPY map lookup). */
function toDayKey(s: string): string {
  if (/^\d{9,11}$/.test(s)) {
    return new Date(parseInt(s, 10) * 1000).toISOString().slice(0, 10);
  }
  return s.slice(0, 10);
}

function fmtDollar(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
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
  height = 420,
}) => {
  const containerRef  = useRef<HTMLDivElement>(null);
  const chartRef      = useRef<IChartApi | null>(null);
  const seriesRef     = useRef<Record<string, ISeriesApi<SeriesType>>>({});
  const roRef         = useRef<ResizeObserver | null>(null);
  const prevIntervalRef = useRef<string>(interval);

  // Derive isIntraday from the actual data content, not just the interval prop.
  // This prevents the race condition where interval prop changes to '1d' but
  // equityData still holds Unix timestamp strings from the previous 4h/1h fetch.
  const isIntraday = useMemo(() => {
    if (interval !== '1d') return true;
    // Check if the data actually contains Unix timestamps (all-digit strings)
    const sample = equityData.find(d => d.date);
    if (sample && /^\d{9,11}$/.test(String(sample.date))) return true;
    return false;
  }, [interval, equityData]);

  const toolbarH   = 32; // px
  const chartH     = height - toolbarH;

  // ── Filter equity curve by period ─────────────────────────────────────
  const filtered = useMemo(() => {
    if (!equityData?.length) return [];
    return filterDataByPeriod(
      equityData.map(d => ({ ...d })),
      'date',
      period,
    ) as EquityDataPoint[];
  }, [equityData, period]);

  // ── Filter daily equity by period (for P&L + Sharpe panes) ────────────
  const filteredDaily = useMemo(() => {
    // Daily points are ISO date strings "YYYY-MM-DD" — they contain a hyphen at index 4.
    // Unix timestamp strings (e.g. "1776625200") are all digits — same length but no hyphens.
    // Must use the hyphen check, not length check, to distinguish them.
    const isIsoDate = (s: string) => /^\d{4}-\d{2}-\d{2}$/.test(s);
    const src = dailyEquity?.length
      ? dailyEquity
      : equityData.filter(d => isIsoDate(String(d.date)));
    if (!src.length) return [];
    return filterDataByPeriod(src.map(d => ({ ...d })), 'date', period) as EquityDataPoint[];
  }, [dailyEquity, equityData, period]);

  // ── Build all series data ──────────────────────────────────────────────
  const chartData = useMemo(() => {
    if (filtered.length < 2) return null;

    const startEquity = filtered[0].equity;

    // Pane 0: Portfolio area
    const portfolio = filtered.map(d => ({
      time:  toTime(d.date, isIntraday),
      value: d.equity,
    }));

    // Pane 0: SPY scaled to same starting equity
    let spy: Array<{ time: Time; value: number }> | null = null;
    if (spyData?.length) {
      const spyMap = new Map(spyData.map(s => [s.date.slice(0, 10), s.close]));
      const startDay   = toDayKey(filtered[0].date);
      const startSpy   = spyMap.get(startDay)
        ?? [...spyMap.entries()].find(([d]) => d >= startDay)?.[1];
      if (startSpy && startSpy > 0) {
        const scale = startEquity / startSpy;
        const seen  = new Set<string>();
        spy = filtered
          .map(d => {
            const day = toDayKey(d.date);
            const v   = spyMap.get(day);
            if (v == null || seen.has(day)) return null;
            seen.add(day);
            return { time: toTime(d.date, isIntraday), value: v * scale };
          })
          .filter(Boolean) as Array<{ time: Time; value: number }>;
        if (spy.length < 2) spy = null;
      }
    }

    // Pane 0: Realized P&L line
    let realized: Array<{ time: Time; value: number }> | null = null;
    if (filtered.some(d => d.realized != null)) {
      const startR = filtered[0].realized ?? 0;
      realized = filtered
        .filter(d => d.realized != null)
        .map(d => ({
          time:  toTime(d.date, isIntraday),
          value: startEquity + ((d.realized ?? 0) - startR),
        }));
      if (realized.length < 2) realized = null;
    }

    // Pane 1: Daily P&L histogram (always daily)
    let pnlBars: Array<{ time: Time; value: number; color: string }> | null = null;
    if (filteredDaily.length >= 2) {
      const seen = new Set<number | string>();
      const bars = filteredDaily.slice(1).map((d, i) => {
        const pnl = d.equity - filteredDaily[i].equity;
        if (!Number.isFinite(pnl) || !d.equity || !filteredDaily[i].equity) return null;
        const t = toTime(d.date, isIntraday);
        // Deduplicate: skip if this time value already appeared
        const key = t as number | string;
        if (seen.has(key)) return null;
        seen.add(key);
        return {
          time:  t,
          value: pnl,
          color: pnl >= 0 ? THEME.pnlPos : THEME.pnlNeg,
        };
      }).filter(Boolean) as Array<{ time: Time; value: number; color: string }>;
      if (bars.length >= 2) pnlBars = bars;
    }

    // Pane 2: Rolling 30d Sharpe (always daily)
    let sharpe: Array<{ time: Time; value: number }> | null = null;
    if (filteredDaily.length >= 32) {
      const returns: number[] = [];
      for (let i = 1; i < filteredDaily.length; i++) {
        const prev = filteredDaily[i - 1].equity;
        const curr = filteredDaily[i].equity;
        returns.push(prev > 0 ? (curr - prev) / prev : 0);
      }
      const pts: Array<{ time: Time; value: number }> = [];
      for (let i = 29; i < returns.length; i++) {
        const dateIdx = i + 1;
        if (dateIdx >= filteredDaily.length) break;
        const window = returns.slice(i - 29, i + 1);
        const mean   = window.reduce((s, v) => s + v, 0) / 30;
        const std    = Math.sqrt(window.reduce((s, v) => s + (v - mean) ** 2, 0) / 30) || 0.0001;
        const val    = Math.round((mean / std) * Math.sqrt(252) * 100) / 100;
        if (Number.isFinite(val)) {
          pts.push({ time: toTime(filteredDaily[dateIdx].date, isIntraday), value: val });
        }
      }
      if (pts.length >= 2) sharpe = pts;
    }

    // Header stats
    const lastEquity  = filtered[filtered.length - 1].equity;
    const totalReturn = ((lastEquity - startEquity) / startEquity) * 100;

    return { portfolio, spy, realized, pnlBars, sharpe, totalReturn, lastEquity };
  }, [filtered, filteredDaily, spyData, isIntraday]);

  // ── Build / rebuild chart ──────────────────────────────────────────────
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const intervalChanged = prevIntervalRef.current !== interval;
    prevIntervalRef.current = interval;

    // In-place update: period changed but interval (time format) did not
    if (chartRef.current && !intervalChanged && seriesRef.current['portfolio']) {
      if (!chartData) return;
      try {
        seriesRef.current['portfolio'].setData(chartData.portfolio as any);
        if (chartData.spy && seriesRef.current['spy']) {
          seriesRef.current['spy'].setData(chartData.spy as any);
        }
        if (chartData.realized && seriesRef.current['realized']) {
          seriesRef.current['realized'].setData(chartData.realized as any);
        }
        if (chartData.pnlBars && seriesRef.current['pnl']) {
          seriesRef.current['pnl'].setData(chartData.pnlBars as any);
        }
        if (chartData.sharpe && seriesRef.current['sharpe']) {
          seriesRef.current['sharpe'].setData(chartData.sharpe as any);
        }
        chartRef.current.timeScale().fitContent();
        return;
      } catch {
        // Fall through to full rebuild on any error
      }
    }

    // Full rebuild
    roRef.current?.disconnect();
    chartRef.current?.remove();
    chartRef.current = null;
    seriesRef.current = {};
    el.innerHTML = '';

    if (!chartData) return;

    const hasPnl    = !!chartData.pnlBars;
    const hasSharpe = !!chartData.sharpe;

    // Calculate pane heights in pixels
    const pane0H = hasPnl || hasSharpe
      ? Math.round(chartH * PANE_HEIGHTS.equity)
      : chartH;
    const pane1H = hasPnl    ? Math.round(chartH * PANE_HEIGHTS.pnl)    : 0;
    const pane2H = hasSharpe ? Math.round(chartH * PANE_HEIGHTS.sharpe)  : 0;

    const chart = createChart(el, {
      width:  el.clientWidth,
      height: chartH,
      layout: {
        background:   { type: ColorType.Solid, color: THEME.bg },
        textColor:    THEME.text,
        fontFamily:   "'JetBrains Mono', 'Courier New', monospace",
        fontSize:     11,
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
        borderColor:  THEME.grid,
        timeVisible:  isIntraday,
        rightOffset:  8,
        barSpacing:   8,
        fixLeftEdge:  true,
        fixRightEdge: true,
      },
      leftPriceScale: {
        visible:      true,
        borderColor:  THEME.grid,
        scaleMargins: { top: 0.06, bottom: 0.04 },
      },
      rightPriceScale: { visible: false },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale:  { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // Set pane 0 height
    chart.panes()[0].setHeight(pane0H);

    // ── Pane 0: SPY (behind portfolio) ────────────────────────────────
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
      s.setData(chartData.spy as any);
      seriesRef.current['spy'] = s;
    }

    // ── Pane 0: Realized P&L line ──────────────────────────────────────
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
      s.setData(chartData.realized as any);
      seriesRef.current['realized'] = s;
    }

    // ── Pane 0: Portfolio area (on top) ────────────────────────────────
    const portfolio = chart.addSeries(AreaSeries, {
      lineColor:        THEME.portfolio,
      topColor:         'rgba(59,130,246,0.18)',
      bottomColor:      'rgba(59,130,246,0.01)',
      lineWidth:        2,
      priceScaleId:     'left',
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
    }, 0);
    portfolio.setData(chartData.portfolio as any);
    seriesRef.current['portfolio'] = portfolio;

    // ── Pane 1: Daily P&L histogram ────────────────────────────────────
    if (hasPnl && pane1H > 0) {
      const pane1 = chart.addPane();
      pane1.setHeight(pane1H);

      const pnl = chart.addSeries(HistogramSeries, {
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
      }, pane1.paneIndex());
      pnl.setData(chartData.pnlBars as any);
      seriesRef.current['pnl'] = pnl;
    }

    // ── Pane 2: Rolling 30d Sharpe ─────────────────────────────────────
    if (hasSharpe && pane2H > 0) {
      const pane2 = chart.addPane();
      pane2.setHeight(pane2H);

      // Zero reference line
      const zeroLine = chart.addSeries(LineSeries, {
        color:            THEME.sharpeZero,
        lineWidth:        1,
        lineStyle:        LineStyle.Dashed,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: () => '', minMove: 0.01 },
      }, pane2.paneIndex());
      const sharpeData = chartData.sharpe!;
      zeroLine.setData([
        { time: sharpeData[0].time,                    value: 0 },
        { time: sharpeData[sharpeData.length - 1].time, value: 0 },
      ]);

      const sharpe = chart.addSeries(LineSeries, {
        color:            THEME.sharpe,
        lineWidth:        1,
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: (v: number) => v.toFixed(2), minMove: 0.01 },
      }, pane2.paneIndex());
      sharpe.setData(chartData.sharpe as any);
      seriesRef.current['sharpe'] = sharpe;
    }

    chart.timeScale().fitContent();

    // ── ResizeObserver ─────────────────────────────────────────────────
    const ro = new ResizeObserver(entries => {
      for (const e of entries) {
        const w = Math.round(e.contentRect.width);
        if (w > 0) chart.applyOptions({ width: w });
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
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartData, chartH, isIntraday]);

  // ── Render ─────────────────────────────────────────────────────────────
  const totalReturn = chartData?.totalReturn ?? null;
  const hasSpy      = !!chartData?.spy;
  const hasRealized = !!chartData?.realized;
  const hasSharpe   = !!chartData?.sharpe;
  const hasPnl      = !!chartData?.pnlBars;

  return (
    <div className="w-full flex flex-col">
      {/* ── Toolbar ── */}
      <div className="flex items-center justify-between px-0.5 mb-1 shrink-0" style={{ height: toolbarH }}>
        {/* Period + interval selectors */}
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
            <span className="w-3 h-[2px] bg-blue-500 inline-block rounded" />
            Equity
          </span>
          {hasRealized && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 inline-block" style={{ borderTop: '1.5px dashed #22c55e' }} />
              Realised
            </span>
          )}
          {hasSpy && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 inline-block" style={{ borderTop: '1.5px dashed #6b7280' }} />
              SPY
            </span>
          )}
          {hasPnl && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 h-[2px] bg-green-500/60 inline-block rounded" />
              P&L
            </span>
          )}
          {hasSharpe && (
            <span className="flex items-center gap-1 text-gray-600">
              <span className="w-3 h-[2px] bg-violet-400/60 inline-block rounded" />
              Sharpe
            </span>
          )}
        </div>
      </div>

      {/* ── Chart container ── */}
      {chartData ? (
        <div ref={containerRef} style={{ width: '100%', height: chartH }} />
      ) : (
        <div
          className="flex items-center justify-center text-gray-700 text-xs font-mono"
          style={{ height: chartH }}
        >
          No data
        </div>
      )}
    </div>
  );
};
