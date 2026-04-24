/**
 * PortfolioEquityChart
 *
 * A ground-up rewrite of the equity curve chart for AlphaCent.
 *
 * Design (quant-first):
 *  - Single lightweight-charts instance, two price scales
 *  - Left scale  : absolute equity in dollars (portfolio + SPY scaled to same start)
 *  - Right scale : drawdown % (0 to -N%) as a red histogram
 *  - Realized P&L line on the left scale (dashed green)
 *  - Period selector filters data client-side (no re-fetch)
 *  - Interval selector triggers parent re-fetch (1d / 4h / 1h)
 *  - Handles both "YYYY-MM-DD" and Unix-timestamp data from backend
 *  - No normalization, no separate pane sync, no priceScaleId hacks
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
  /** "YYYY-MM-DD" or "YYYY-MM-DD HH:MM" or Unix timestamp string */
  date: string;
  equity: number;
  /** Cumulative realized P&L (optional) */
  realized?: number | null;
}

export interface SpyDataPoint {
  date: string;
  close: number;
}

export interface PortfolioEquityChartProps {
  equityData: EquityDataPoint[];
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
  bg:         '#0a0e1a',
  grid:       '#1a2035',
  text:       '#6b7280',
  crosshair:  '#374151',
  portfolio:  '#3b82f6',
  spy:        '#6b7280',
  realized:   '#22c55e',
  drawdown:   'rgba(239,68,68,0.5)',
  drawdownLine: 'rgba(239,68,68,0.8)',
};

// ── Helpers ───────────────────────────────────────────────────────────────

/** Convert any date string or unix timestamp to lightweight-charts Time */
function toTime(s: string): Time {
  // Unix timestamp (all digits, 9-11 chars)
  if (/^\d{9,11}$/.test(s)) return parseInt(s, 10) as Time;
  // Sub-daily: "YYYY-MM-DD HH:MM" → convert to Unix timestamp for proper intraday rendering
  if (s.length > 10 && s[10] === ' ') {
    try {
      const dt = new Date(s.replace(' ', 'T') + ':00Z');
      if (!isNaN(dt.getTime())) return Math.floor(dt.getTime() / 1000) as Time;
    } catch { /* fall through */ }
  }
  // Daily: "YYYY-MM-DD"
  return s.slice(0, 10) as Time;
}

/** Format dollar value for axis labels */
function fmtDollar(v: number): string {
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
  if (Math.abs(v) >= 1_000)     return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

// ── Main Component ────────────────────────────────────────────────────────

export const PortfolioEquityChart: FC<PortfolioEquityChartProps> = ({
  equityData,
  spyData,
  period,
  onPeriodChange,
  interval = '1d',
  onIntervalChange,
  height = 380,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const seriesRef    = useRef<Record<string, ISeriesApi<SeriesType>>>({});
  const roRef        = useRef<ResizeObserver | null>(null);

  // ── Filter data by period ──────────────────────────────────────────────
  const filtered = useMemo(() => {
    if (!equityData?.length) return [];
    return filterDataByPeriod(
      equityData.map(d => ({ ...d })),
      'date',
      period,
    ) as EquityDataPoint[];
  }, [equityData, period]);

  // ── Derived series data ────────────────────────────────────────────────
  const chartData = useMemo(() => {
    if (filtered.length < 2) return null;

    const startEquity = filtered[0].equity;

    // Portfolio area
    const portfolio = filtered.map(d => ({
      time: toTime(d.date),
      value: d.equity,
    }));

    // Drawdown histogram (right scale)
    let peak = startEquity;
    const drawdown = filtered.map(d => {
      if (d.equity > peak) peak = d.equity;
      const dd = peak > 0 ? ((d.equity - peak) / peak) * 100 : 0;
      return {
        time: toTime(d.date),
        value: dd,
        color: dd < -5 ? 'rgba(239,68,68,0.7)' : 'rgba(239,68,68,0.4)',
      };
    });

    // SPY scaled to same starting equity
    // For intraday intervals, SPY is daily-only data — use the portfolio bar's own timestamp
    // so all series on the chart share the same time format (Unix vs BusinessDay).
    let spy: Array<{ time: Time; value: number }> | null = null;
    if (spyData?.length) {
      const spyMap = new Map(spyData.map(s => [s.date.slice(0, 10), s.close]));
      const startDate = filtered[0].date.slice(0, 10);
      const startSpy  = spyMap.get(startDate)
        ?? [...spyMap.entries()].find(([d]) => d >= startDate)?.[1];
      if (startSpy && startSpy > 0) {
        const scale = startEquity / startSpy;
        const seenDates = new Set<string>();
        spy = filtered
          .map(d => {
            const dayKey = d.date.slice(0, 10);
            const v = spyMap.get(dayKey);
            if (v == null) return null;
            // For intraday: emit once per day using the portfolio bar's own timestamp
            // so SPY time format matches portfolio (Unix timestamp, not BusinessDay string)
            if (seenDates.has(dayKey)) return null;
            seenDates.add(dayKey);
            return { time: toTime(d.date), value: v * scale };
          })
          .filter(Boolean) as Array<{ time: Time; value: number }>;
        if (spy.length < 2) spy = null;
      }
    }

    // Realized P&L line (absolute: starting equity + cumulative realized)
    let realized: Array<{ time: Time; value: number }> | null = null;
    const hasRealized = filtered.some(d => d.realized != null);
    if (hasRealized) {
      const startRealized = filtered[0].realized ?? 0;
      realized = filtered
        .filter(d => d.realized != null)
        .map(d => ({
          time: toTime(d.date),
          value: startEquity + ((d.realized ?? 0) - startRealized),
        }));
      if (realized.length < 2) realized = null;
    }

    // Stats for header
    const lastEquity = filtered[filtered.length - 1].equity;
    const totalReturn = ((lastEquity - startEquity) / startEquity) * 100;
    const maxDD = Math.min(...drawdown.map(d => d.value));

    return { portfolio, drawdown, spy, realized, totalReturn, maxDD, lastEquity };
  }, [filtered, spyData]);

  // ── Create / destroy chart ─────────────────────────────────────────────
  // Only recreate the chart when height changes or when the time format changes
  // (switching between daily BusinessDay strings and intraday Unix timestamps).
  // For period changes (client-side filter), just update series data in place.
  const prevIntervalRef = useRef<string>(interval ?? '1d');

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const intervalChanged = prevIntervalRef.current !== (interval ?? '1d');
    prevIntervalRef.current = interval ?? '1d';

    // If chart already exists and only data changed (not interval/height), update in place
    if (chartRef.current && !intervalChanged && seriesRef.current['portfolio']) {
      if (!chartData) return;
      try {
        if (chartData.spy && seriesRef.current['spy']) {
          seriesRef.current['spy'].setData(chartData.spy as any);
        } else if (!chartData.spy && seriesRef.current['spy']) {
          // spy disappeared — need full rebuild
        }
        if (chartData.realized && seriesRef.current['realized']) {
          seriesRef.current['realized'].setData(chartData.realized as any);
        }
        seriesRef.current['portfolio'].setData(chartData.portfolio as any);
        seriesRef.current['drawdown'].setData(chartData.drawdown as any);
        chartRef.current.timeScale().fitContent();
        return; // skip full rebuild
      } catch {
        // fall through to full rebuild on any error
      }
    }

    // Full rebuild (first mount, interval change, or height change)
    roRef.current?.disconnect();
    chartRef.current?.remove();
    seriesRef.current = {};

    if (!chartData) return;

    const chart = createChart(el, {
      width:  el.clientWidth,
      height: height - 36, // subtract toolbar height
      layout: {
        background: { type: ColorType.Solid, color: THEME.bg },
        textColor:  THEME.text,
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize:   11,
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: THEME.grid, style: LineStyle.Dotted },
        horzLines: { color: THEME.grid, style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
        vertLine: { color: THEME.crosshair, labelBackgroundColor: '#1f2937' },
        horzLine: { color: THEME.crosshair, labelBackgroundColor: '#1f2937' },
      },
      timeScale: {
        borderColor:  THEME.grid,
        timeVisible:  interval !== '1d', // show HH:MM for intraday
        rightOffset:  8,
        barSpacing:   8,
        fixLeftEdge:  true,
        fixRightEdge: true,
      },
      leftPriceScale: {
        visible:     true,
        borderColor: THEME.grid,
        scaleMargins: { top: 0.08, bottom: 0.28 }, // leave room for drawdown
      },
      rightPriceScale: {
        visible:     true,
        borderColor: THEME.grid,
        scaleMargins: { top: 0.72, bottom: 0.02 }, // drawdown occupies bottom 28%
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale:  { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // ── SPY (behind portfolio) ─────────────────────────────────────────
    if (chartData.spy) {
      const s = chart.addSeries(LineSeries, {
        color:            THEME.spy,
        lineWidth:        1,
        lineStyle:        LineStyle.Dashed,
        priceScaleId:     'left',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
      });
      s.setData(chartData.spy);
      seriesRef.current['spy'] = s;
    }

    // ── Realized P&L line ──────────────────────────────────────────────
    if (chartData.realized) {
      const s = chart.addSeries(LineSeries, {
        color:            THEME.realized,
        lineWidth:        1,
        lineStyle:        LineStyle.Dashed,
        priceScaleId:     'left',
        lastValueVisible: false,
        priceLineVisible: false,
        priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
      });
      s.setData(chartData.realized);
      seriesRef.current['realized'] = s;
    }

    // ── Portfolio area (on top) ────────────────────────────────────────
    const portfolio = chart.addSeries(AreaSeries, {
      lineColor:        THEME.portfolio,
      topColor:         'rgba(59,130,246,0.18)',
      bottomColor:      'rgba(59,130,246,0.01)',
      lineWidth:        2,
      priceScaleId:     'left',
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
    });
    portfolio.setData(chartData.portfolio);
    seriesRef.current['portfolio'] = portfolio;

    // ── Drawdown histogram (right scale, bottom strip) ─────────────────
    const dd = chart.addSeries(HistogramSeries, {
      color:            THEME.drawdown,
      priceScaleId:     'right',
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: (v: number) => `${v.toFixed(1)}%`, minMove: 0.01 },
    });
    dd.setData(chartData.drawdown);
    seriesRef.current['drawdown'] = dd;

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
  // Recreate chart whenever data or height changes
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [chartData, height]);

  // ── Render ─────────────────────────────────────────────────────────────
  const hasSpy      = !!chartData?.spy;
  const hasRealized = !!chartData?.realized;
  const totalReturn = chartData?.totalReturn ?? null;
  const maxDD       = chartData?.maxDD ?? null;

  return (
    <div className="w-full flex flex-col">
      {/* ── Toolbar ── */}
      <div className="flex items-center justify-between px-0.5 mb-1 h-[28px] shrink-0">
        {/* Left: period + interval */}
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

        {/* Right: stats + legend */}
        <div className="flex items-center gap-3 text-[10px] font-mono">
          {totalReturn != null && (
            <span className={cn('font-semibold', totalReturn >= 0 ? 'text-green-400' : 'text-red-400')}>
              {totalReturn >= 0 ? '+' : ''}{totalReturn.toFixed(2)}%
            </span>
          )}
          {maxDD != null && maxDD < 0 && (
            <span className="text-red-400/70">DD {maxDD.toFixed(2)}%</span>
          )}
          <span className="flex items-center gap-1 text-gray-600">
            <span className="w-3 h-[2px] bg-blue-500 inline-block rounded" />
            Total
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
          <span className="flex items-center gap-1 text-gray-600">
            <span className="w-3 h-[2px] bg-red-500/60 inline-block rounded" />
            DD
          </span>
        </div>
      </div>

      {/* ── Chart container ── */}
      {chartData ? (
        <div ref={containerRef} style={{ width: '100%', height: height - 36 }} />
      ) : (
        <div
          className="flex items-center justify-center text-gray-700 text-xs font-mono"
          style={{ height: height - 36 }}
        >
          No data
        </div>
      )}
    </div>
  );
};
