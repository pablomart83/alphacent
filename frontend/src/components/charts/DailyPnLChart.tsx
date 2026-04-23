/**
 * DailyPnLChart — Daily P&L histogram for AlphaCent overview.
 *
 * Ground-up rewrite using a single createChart instance.
 * - Green bars for positive days, red for negative
 * - Baseline at 0
 * - Proper date axis aligned with the equity curve
 * - Always uses daily data (one bar per calendar day)
 */

import { type FC, useEffect, useRef, useMemo } from 'react';
import {
  createChart,
  ColorType,
  CrosshairMode,
  LineStyle,
  HistogramSeries,
  LineSeries,
  type IChartApi,
  type Time,
} from 'lightweight-charts';

export interface DailyPnLPoint {
  date: string; // "YYYY-MM-DD"
  pnl: number;
}

export interface DailyPnLChartProps {
  data: DailyPnLPoint[];
  height?: number;
}

const THEME = {
  bg:       '#0a0e1a',
  grid:     '#1a2035',
  text:     '#6b7280',
  crosshair:'#374151',
  positive: 'rgba(34,197,94,0.75)',
  negative: 'rgba(239,68,68,0.75)',
  zero:     '#374151',
};

function fmtDollar(v: number): string {
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
  return `$${v.toFixed(0)}`;
}

export const DailyPnLChart: FC<DailyPnLChartProps> = ({ data, height = 90 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef     = useRef<IChartApi | null>(null);
  const roRef        = useRef<ResizeObserver | null>(null);

  // Deduplicate to one point per calendar day (take last value per day)
  const dailyData = useMemo(() => {
    const map = new Map<string, number>();
    for (const d of data) {
      const day = d.date.slice(0, 10);
      if (day.match(/^\d{4}-\d{2}-\d{2}$/)) map.set(day, d.pnl);
    }
    return [...map.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, pnl]) => ({ date, pnl }));
  }, [data]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    roRef.current?.disconnect();
    chartRef.current?.remove();

    if (dailyData.length < 2) return;

    const chart = createChart(el, {
      width:  el.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: THEME.bg },
        textColor:  THEME.text,
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize:   10,
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
        timeVisible:  false,
        rightOffset:  8,
        barSpacing:   8,
        fixLeftEdge:  true,
        fixRightEdge: true,
      },
      rightPriceScale: {
        visible:     true,
        borderColor: THEME.grid,
        scaleMargins: { top: 0.1, bottom: 0.1 },
      },
      leftPriceScale:  { visible: false },
      handleScroll:    { mouseWheel: false, pressedMouseMove: false },
      handleScale:     { mouseWheel: false, pinch: false },
    });

    chartRef.current = chart;

    // Zero baseline
    const baseline = chart.addSeries(LineSeries, {
      color:            THEME.zero,
      lineWidth:        1,
      lineStyle:        LineStyle.Solid,
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: () => '', minMove: 1 },
    });
    baseline.setData([
      { time: dailyData[0].date as Time,                    value: 0 },
      { time: dailyData[dailyData.length - 1].date as Time, value: 0 },
    ]);

    // P&L histogram
    const hist = chart.addSeries(HistogramSeries, {
      lastValueVisible: false,
      priceLineVisible: false,
      priceFormat:      { type: 'custom', formatter: fmtDollar, minMove: 1 },
    });    hist.setData(
      dailyData.map(d => ({
        time:  d.date as Time,
        value: d.pnl,
        color: d.pnl >= 0 ? THEME.positive : THEME.negative,
      })),
    );

    chart.timeScale().fitContent();

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
    };
  }, [dailyData, height]);

  if (dailyData.length < 2) return null;

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};
