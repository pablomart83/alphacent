/**
 * TvMultiPane — Multiple synchronized TradingView Lightweight Charts stacked vertically.
 *
 * Each pane is an independent chart instance sharing the same time axis via
 * crosshair synchronization. Panes are separated by a thin divider.
 *
 * Usage:
 *   <TvMultiPane
 *     panes={[
 *       { id: 'price', series: [...], height: 240, label: 'Price' },
 *       { id: 'volume', series: [...], height: 80, label: 'Volume' },
 *       { id: 'rsi', series: [...], height: 80, label: 'RSI' },
 *     ]}
 *   />
 */

import { type FC, useRef, useEffect, memo } from 'react';
import {
  createChart,
  type IChartApi,
  type ISeriesApi,
  type SeriesType,
  type Time,
  type MouseEventParams,
  ColorType,
  CrosshairMode,
  LineStyle,
  AreaSeries,
  LineSeries,
  CandlestickSeries,
  HistogramSeries,
  BaselineSeries,
} from 'lightweight-charts';
import type { TvSeriesConfig, TvDataPoint } from './TvChart';

// Re-export types for convenience
export type { TvSeriesConfig, TvDataPoint };

const THEME = {
  bg: '#0a0e1a',
  grid: '#1f2937',
  text: '#9ca3af',
  crosshair: '#6b7280',
  up: '#22c55e',
  down: '#ef4444',
  line: '#3b82f6',
  area: 'rgba(59, 130, 246, 0.15)',
  areaLine: '#3b82f6',
};

export interface TvPane {
  id: string;
  series: TvSeriesConfig[];
  height: number;
  label?: string;
  showTimeScale?: boolean;
  showPriceScale?: boolean;
}

export interface TvMultiPaneProps {
  panes: TvPane[];
  className?: string;
}

function toChartTime(t: string | number): Time {
  if (typeof t === 'number') return t as Time;
  const s = String(t);
  // Unix timestamp string (all digits) → parse as number
  if (/^\d{9,11}$/.test(s)) return parseInt(s, 10) as Time;
  // Sub-daily "YYYY-MM-DD HH:MM" → UTC Unix timestamp (matches PortfolioEquityChart.toTime)
  if (s.length > 10 && s[10] === ' ') {
    try {
      const dt = new Date(s.replace(' ', 'T') + ':00Z');
      if (!isNaN(dt.getTime())) return Math.floor(dt.getTime() / 1000) as Time;
    } catch {}
  }
  // Daily "YYYY-MM-DD" → BusinessDay string
  return s.slice(0, 10) as Time;
}

function getSeriesDef(type: TvSeriesConfig['type']) {
  switch (type) {
    case 'area': return AreaSeries as any;
    case 'line': return LineSeries as any;
    case 'candlestick': return CandlestickSeries as any;
    case 'histogram': return HistogramSeries as any;
    case 'baseline': return BaselineSeries as any;
    default: return LineSeries as any;
  }
}

function buildOpts(cfg: TvSeriesConfig): Record<string, unknown> {
  const base: Record<string, unknown> = {};
  if (cfg.priceScaleId) base.priceScaleId = cfg.priceScaleId;
  switch (cfg.type) {
    case 'area':
      return { ...base, lineColor: cfg.lineColor || cfg.color || THEME.areaLine, topColor: cfg.topColor || THEME.area, bottomColor: cfg.bottomColor || 'transparent', lineWidth: cfg.lineWidth || 2 };
    case 'line':
      return { ...base, color: cfg.color || THEME.line, lineWidth: cfg.lineWidth || 2, lineStyle: cfg.dashed ? LineStyle.Dashed : LineStyle.Solid };
    case 'candlestick':
      return { ...base, upColor: THEME.up, downColor: THEME.down, borderUpColor: THEME.up, borderDownColor: THEME.down, wickUpColor: THEME.up, wickDownColor: THEME.down };
    case 'histogram':
      return { ...base, color: cfg.color || 'rgba(59,130,246,0.4)', priceFormat: { type: 'volume' as const }, priceScaleId: cfg.priceScaleId || 'volume' };
    case 'baseline':
      return { ...base, baseValue: { type: 'price' as const, price: cfg.baseValue ?? 0 }, topFillColor1: cfg.topFillColor1 || 'rgba(34,197,94,0.2)', topFillColor2: cfg.topFillColor2 || 'rgba(34,197,94,0.02)', bottomFillColor1: cfg.bottomFillColor1 || 'rgba(239,68,68,0.02)', bottomFillColor2: cfg.bottomFillColor2 || 'rgba(239,68,68,0.2)', topLineColor: cfg.topLineColor || THEME.up, bottomLineColor: cfg.bottomLineColor || THEME.down, lineWidth: cfg.lineWidth || 2 };
    default: return base;
  }
}

function setSeriesData(s: ISeriesApi<SeriesType>, cfg: TvSeriesConfig) {
  if (!cfg.data.length) return;
  const chartData = cfg.data.map((d) => {
    const t = toChartTime(d.time);
    if (cfg.type === 'candlestick') return { time: t, open: d.open ?? 0, high: d.high ?? 0, low: d.low ?? 0, close: d.close ?? 0 };
    if (cfg.type === 'histogram') return { time: t, value: d.value ?? d.close ?? 0, color: d.color };
    return { time: t, value: d.value ?? d.close ?? 0 };
  });
  chartData.sort((a, b) => {
    const ta = typeof a.time === 'number' ? a.time : String(a.time);
    const tb = typeof b.time === 'number' ? b.time : String(b.time);
    if (typeof ta === 'number' && typeof tb === 'number') return ta - tb;
    return String(ta).localeCompare(String(tb));
  });
  s.setData(chartData as any);
}

const TvMultiPaneInner: FC<TvMultiPaneProps> = ({ panes, className }) => {
  const containerRefs = useRef<(HTMLDivElement | null)[]>([]);
  const chartsRef = useRef<IChartApi[]>([]);
  const seriesMapsRef = useRef<Map<string, ISeriesApi<SeriesType>>[]>([]);

  useEffect(() => {
    // Clean up previous charts
    chartsRef.current.forEach(c => { try { c.remove(); } catch {} });
    chartsRef.current = [];
    seriesMapsRef.current = [];

    const charts: IChartApi[] = [];

    panes.forEach((pane, idx) => {
      const el = containerRefs.current[idx];
      if (!el) return;

      const isLast = idx === panes.length - 1;
      const chart = createChart(el, {
        width: el.clientWidth,
        height: pane.height,
        layout: {
          background: { type: ColorType.Solid, color: THEME.bg },
          textColor: THEME.text,
          fontFamily: "'JetBrains Mono', 'Courier New', monospace",
          fontSize: 11,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: THEME.grid, style: LineStyle.Dotted },
          horzLines: { color: THEME.grid, style: LineStyle.Dotted },
        },
        crosshair: {
          mode: CrosshairMode.Normal,
          vertLine: { color: THEME.crosshair, labelBackgroundColor: '#374151' },
          horzLine: { color: THEME.crosshair, labelBackgroundColor: '#374151' },
        },
        timeScale: {
          visible: pane.showTimeScale ?? isLast,
          borderColor: THEME.grid,
          timeVisible: false,
          rightOffset: 5,
          barSpacing: 6,
        },
        rightPriceScale: {
          visible: pane.showPriceScale ?? true,
          borderColor: THEME.grid,
        },
        handleScroll: { mouseWheel: true, pressedMouseMove: true },
        handleScale: { mouseWheel: true, pinch: true },
      });

      charts.push(chart);
      const seriesMap = new Map<string, ISeriesApi<SeriesType>>();

      for (const cfg of pane.series) {
        const def = getSeriesDef(cfg.type);
        const opts = buildOpts(cfg);
        const s = chart.addSeries(def, opts as any);
        if (cfg.type === 'histogram' && (cfg.priceScaleId === 'volume' || !cfg.priceScaleId)) {
          chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
        }
        setSeriesData(s, cfg);
        seriesMap.set(cfg.id, s);
      }

      seriesMapsRef.current[idx] = seriesMap;
      chart.timeScale().fitContent();
    });

    chartsRef.current = charts;

    // ── Crosshair synchronization ──────────────────────────────────────
    // When the user moves the crosshair on any chart, sync all others.
    const handlers: Array<(params: MouseEventParams<Time>) => void> = [];

    charts.forEach((chart, idx) => {
      const handler = (params: MouseEventParams<Time>) => {
        if (!params.time) return;
        charts.forEach((other, otherIdx) => {
          if (otherIdx === idx) return;
          // Get a value from the first series data entry for the crosshair position
          const seriesEntries = Array.from(params.seriesData.entries());
          const firstEntry = seriesEntries[0];
          const val = firstEntry
            ? (() => {
                const d = firstEntry[1] as any;
                return d?.value ?? d?.close ?? 0;
              })()
            : 0;
          // Get the first series of the target chart for positioning
          const targetSeriesMap = seriesMapsRef.current[otherIdx];
          if (!targetSeriesMap) return;
          const targetSeries = targetSeriesMap.values().next().value;
          if (!targetSeries) return;
          try {
            other.setCrosshairPosition(val, params.time!, targetSeries as any);
          } catch {}
        });
      };
      chart.subscribeCrosshairMove(handler);
      handlers.push(handler);
    });

    // ── ResizeObserver — sync all chart widths ─────────────────────────
    const ros: ResizeObserver[] = [];
    charts.forEach((chart, idx) => {
      const el = containerRefs.current[idx];
      if (!el) return;
      const ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width } = entry.contentRect;
          if (width > 0) chart.applyOptions({ width });
        }
      });
      ro.observe(el);
      ros.push(ro);
    });

    return () => {
      handlers.forEach((h, idx) => { try { charts[idx]?.unsubscribeCrosshairMove(h); } catch {} });
      ros.forEach(ro => ro.disconnect());
      charts.forEach(c => { try { c.remove(); } catch {} });
      chartsRef.current = [];
      seriesMapsRef.current = [];
    };
  }, [panes]);

  const totalHeight = panes.reduce((sum, p) => sum + p.height, 0);

  return (
    <div className={className} style={{ width: '100%', height: totalHeight }}>
      {panes.map((pane, idx) => (
        <div key={pane.id} style={{ position: 'relative' }}>
          {pane.label && (
            <div style={{
              position: 'absolute', top: 4, left: 8, zIndex: 10,
              fontSize: 10, color: '#6b7280', fontFamily: 'monospace', pointerEvents: 'none',
            }}>
              {pane.label}
            </div>
          )}
          <div
            ref={(el) => { containerRefs.current[idx] = el; }}
            style={{ width: '100%', height: pane.height, overflow: 'hidden' }}
          />
          {idx < panes.length - 1 && (
            <div style={{ height: 1, backgroundColor: '#1f2937' }} />
          )}
        </div>
      ))}
    </div>
  );
};

export const TvMultiPane = memo(TvMultiPaneInner);
