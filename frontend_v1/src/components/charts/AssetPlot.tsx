/**
 * AssetPlot — Price chart with OHLC candlesticks, volume pane, buy/sell markers,
 * and auto-detected support/resistance levels.
 *
 * Uses TvMultiPane for synchronized panes:
 *   Pane 0 (tall): Candlestick price + order markers + S/R levels
 *   Pane 1 (short): Volume histogram
 */

import { type FC, useMemo } from 'react';
import type { TvSeriesConfig } from './TvChart';
import { createSeriesMarkers } from 'lightweight-charts';

export interface PricePoint {
  date: string;
  price: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  volume?: number;
}

export interface OrderAnnotation {
  date: string;
  price: number;
  side: 'BUY' | 'SELL';
  quantity?: number;
}

export interface AssetPlotProps {
  priceData: PricePoint[];
  orders?: OrderAnnotation[];
  symbol: string;
  height?: number;
}

// ── Support/Resistance detection ──────────────────────────────────────────
// Finds local swing highs/lows over a lookback window.
// Returns the top N most significant levels.
function detectSupportResistance(
  data: Array<{ date: string; high: number; low: number; close: number }>,
  lookback = 5,
  topN = 4,
): Array<{ price: number; type: 'support' | 'resistance' }> {
  if (data.length < lookback * 2 + 1) return [];

  const levels: Array<{ price: number; type: 'support' | 'resistance'; strength: number }> = [];

  for (let i = lookback; i < data.length - lookback; i++) {
    const window = data.slice(i - lookback, i + lookback + 1);
    const highs = window.map(d => d.high);
    const lows = window.map(d => d.low);
    const maxHigh = Math.max(...highs);
    const minLow = Math.min(...lows);

    // Swing high
    if (data[i].high === maxHigh) {
      levels.push({ price: data[i].high, type: 'resistance', strength: data[i].high });
    }
    // Swing low
    if (data[i].low === minLow) {
      levels.push({ price: data[i].low, type: 'support', strength: -data[i].low });
    }
  }

  // Also add 52-week high/low
  if (data.length > 0) {
    const allHighs = data.map(d => d.high);
    const allLows = data.map(d => d.low);
    const yearHigh = Math.max(...allHighs);
    const yearLow = Math.min(...allLows);
    levels.push({ price: yearHigh, type: 'resistance', strength: yearHigh * 2 }); // boost weight
    levels.push({ price: yearLow, type: 'support', strength: -yearLow * 2 });
  }

  // Deduplicate levels within 0.5% of each other
  const deduped: typeof levels = [];
  for (const lvl of levels) {
    const near = deduped.find(d => Math.abs(d.price - lvl.price) / lvl.price < 0.005);
    if (!near) deduped.push(lvl);
  }

  // Sort by strength and take top N of each type
  const resistances = deduped.filter(l => l.type === 'resistance')
    .sort((a, b) => b.strength - a.strength).slice(0, topN / 2);
  const supports = deduped.filter(l => l.type === 'support')
    .sort((a, b) => a.strength - b.strength).slice(0, topN / 2);

  return [...resistances, ...supports];
}

// ── Main Component ─────────────────────────────────────────────────────────

export const AssetPlot: FC<AssetPlotProps> = ({
  priceData,
  orders = [],
  symbol,
  height = 350,
}) => {
  // Normalize and deduplicate price data
  const ohlcvData = useMemo(() => {
    if (!priceData.length) return [];
    const map = new Map<string, PricePoint>();
    for (const d of priceData) {
      const key = d.date.slice(0, 10);
      map.set(key, d);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, d]) => ({
        date,
        open: d.open ?? d.price,
        high: d.high ?? d.price,
        low: d.low ?? d.price,
        close: d.close ?? d.price,
        volume: d.volume ?? 0,
      }));
  }, [priceData]);

  // Detect support/resistance levels
  const srLevels = useMemo(() => detectSupportResistance(ohlcvData), [ohlcvData]);

  // Build order markers
  const markers = useMemo(() =>
    orders
      .map(o => ({
        time: o.date.slice(0, 10),
        position: o.side === 'BUY' ? 'belowBar' as const : 'aboveBar' as const,
        color: o.side === 'BUY' ? '#22c55e' : '#ef4444',
        shape: o.side === 'BUY' ? 'arrowUp' as const : 'arrowDown' as const,
        text: o.side === 'BUY' ? 'B' : 'S',
      }))
      .sort((a, b) => a.time.localeCompare(b.time)),
    [orders]
  );

  // Build price line data for S/R overlays
  // We use line series with price line options — but TvMultiPane doesn't expose
  // the series API directly. Instead we add thin line series for each S/R level.
  const srSeries: TvSeriesConfig[] = useMemo(() =>
    srLevels.map((lvl, i) => ({
      id: `sr_${i}`,
      type: 'line' as const,
      data: ohlcvData.length > 0
        ? [
            { time: ohlcvData[0].date, value: lvl.price },
            { time: ohlcvData[ohlcvData.length - 1].date, value: lvl.price },
          ]
        : [],
      color: lvl.type === 'resistance' ? 'rgba(239,68,68,0.45)' : 'rgba(34,197,94,0.45)',
      lineWidth: 1,
      dashed: true,
    })),
    [srLevels, ohlcvData]
  );

  // Candlestick series
  const candleSeries: TvSeriesConfig = {
    id: 'candles',
    type: 'candlestick',
    data: ohlcvData.map(d => ({
      time: d.date,
      open: d.open,
      high: d.high,
      low: d.low,
      close: d.close,
    })),
  };

  // Volume series
  const volumeSeries: TvSeriesConfig = {
    id: 'volume',
    type: 'histogram',
    data: ohlcvData.map(d => ({
      time: d.date,
      value: d.volume,
      color: d.close >= d.open ? 'rgba(34,197,94,0.4)' : 'rgba(239,68,68,0.4)',
    })),
    priceScaleId: 'volume',
  };

  const priceHeight = Math.round(height * 0.72);
  const volHeight = height - priceHeight;

  // We need to attach markers after chart creation — TvMultiPane handles this
  // via a post-render callback. We pass markers as metadata on the series.
  const priceSeries: TvSeriesConfig[] = [
    candleSeries,
    ...srSeries,
    // Markers are attached via a special 'markers' field we'll handle in TvMultiPane
  ];

  // Attach markers to the candle series via a custom field
  (priceSeries[0] as any).__markers = markers;

  if (ohlcvData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ height }}>
        No price data available for {symbol}
      </div>
    );
  }

  return (
    <AssetPlotWithMarkers
      priceSeries={priceSeries}
      volumeSeries={volumeSeries}
      markers={markers}
      priceHeight={priceHeight}
      volHeight={volHeight}
      srLevels={srLevels}
    />
  );
};

// ── Inner component that handles marker attachment ─────────────────────────
// We need direct series access for createSeriesMarkers, so we use a ref-based approach.

import { useRef, useEffect } from 'react';
import {
  createChart,
  type IChartApi,
  type Time,
  ColorType,
  CrosshairMode,
  LineStyle,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
} from 'lightweight-charts';

const THEME = {
  bg: '#0a0e1a',
  grid: '#1f2937',
  text: '#9ca3af',
  crosshair: '#6b7280',
  up: '#22c55e',
  down: '#ef4444',
};

interface AssetPlotWithMarkersProps {
  priceSeries: TvSeriesConfig[];
  volumeSeries: TvSeriesConfig;
  markers: Array<{ time: string; position: 'belowBar' | 'aboveBar'; color: string; shape: 'arrowUp' | 'arrowDown'; text: string }>;
  priceHeight: number;
  volHeight: number;
  srLevels: Array<{ price: number; type: 'support' | 'resistance' }>;
}

function toTime(t: string | number): Time {
  const s = String(t);
  return (s.length === 10 ? s : s.slice(0, 10)) as Time;
}

const AssetPlotWithMarkers: FC<AssetPlotWithMarkersProps> = ({
  priceSeries, volumeSeries, markers, priceHeight, volHeight, srLevels,
}) => {
  const priceRef = useRef<HTMLDivElement>(null);
  const volRef = useRef<HTMLDivElement>(null);
  const priceChartRef = useRef<IChartApi | null>(null);
  const volChartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!priceRef.current || !volRef.current) return;

    // ── Price chart ──────────────────────────────────────────────────
    const priceChart = createChart(priceRef.current, {
      width: priceRef.current.clientWidth,
      height: priceHeight,
      layout: { background: { type: ColorType.Solid, color: THEME.bg }, textColor: THEME.text, fontFamily: "'JetBrains Mono','Courier New',monospace", fontSize: 11, attributionLogo: false },
      grid: { vertLines: { color: THEME.grid, style: LineStyle.Dotted }, horzLines: { color: THEME.grid, style: LineStyle.Dotted } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: THEME.crosshair, labelBackgroundColor: '#374151' }, horzLine: { color: THEME.crosshair, labelBackgroundColor: '#374151' } },
      timeScale: { visible: false, borderColor: THEME.grid, rightOffset: 5, barSpacing: 6 },
      rightPriceScale: { borderColor: THEME.grid },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    priceChartRef.current = priceChart;

    // Candlestick series
    const candleSeries = priceChart.addSeries(CandlestickSeries, {
      upColor: THEME.up, downColor: THEME.down,
      borderUpColor: THEME.up, borderDownColor: THEME.down,
      wickUpColor: THEME.up, wickDownColor: THEME.down,
    });
    const candleData = priceSeries[0].data.map(d => ({
      time: toTime(d.time), open: d.open ?? 0, high: d.high ?? 0, low: d.low ?? 0, close: d.close ?? 0,
    })).sort((a, b) => String(a.time).localeCompare(String(b.time)));
    candleSeries.setData(candleData as any);

    // Attach order markers
    if (markers.length > 0) {
      const sortedMarkers = [...markers].sort((a, b) => a.time.localeCompare(b.time));
      createSeriesMarkers(candleSeries, sortedMarkers.map(m => ({ ...m, time: toTime(m.time) })) as any);
    }

    // S/R level lines
    for (const lvl of srLevels) {
      if (candleData.length < 2) continue;
      const srLine = priceChart.addSeries(LineSeries, {
        color: lvl.type === 'resistance' ? 'rgba(239,68,68,0.5)' : 'rgba(34,197,94,0.5)',
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      srLine.setData([
        { time: candleData[0].time, value: lvl.price },
        { time: candleData[candleData.length - 1].time, value: lvl.price },
      ] as any);
    }

    priceChart.timeScale().fitContent();

    // ── Volume chart ─────────────────────────────────────────────────
    const volChart = createChart(volRef.current, {
      width: volRef.current.clientWidth,
      height: volHeight,
      layout: { background: { type: ColorType.Solid, color: THEME.bg }, textColor: THEME.text, fontFamily: "'JetBrains Mono','Courier New',monospace", fontSize: 10, attributionLogo: false },
      grid: { vertLines: { color: THEME.grid, style: LineStyle.Dotted }, horzLines: { color: 'transparent' } },
      crosshair: { mode: CrosshairMode.Normal, vertLine: { color: THEME.crosshair, labelBackgroundColor: '#374151' }, horzLine: { visible: false } },
      timeScale: { visible: true, borderColor: THEME.grid, timeVisible: false, rightOffset: 5, barSpacing: 6 },
      rightPriceScale: { borderColor: THEME.grid, scaleMargins: { top: 0.1, bottom: 0 } },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });
    volChartRef.current = volChart;

    const volSeries = volChart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' as const },
      priceScaleId: '',
    });
    volChart.priceScale('').applyOptions({ scaleMargins: { top: 0.1, bottom: 0 } });
    const volData = volumeSeries.data.map(d => ({
      time: toTime(d.time), value: d.value ?? 0, color: d.color,
    })).sort((a, b) => String(a.time).localeCompare(String(b.time)));
    volSeries.setData(volData as any);
    volChart.timeScale().fitContent();

    // ── Crosshair sync ───────────────────────────────────────────────
    const syncHandler = (params: any) => {
      if (!params.time) return;
      try {
        volChart.setCrosshairPosition(
          params.seriesData.values().next().value?.value ?? 0,
          params.time,
          volSeries as any,
        );
      } catch {}
    };
    const syncHandlerVol = (params: any) => {
      if (!params.time) return;
      try {
        priceChart.setCrosshairPosition(
          params.seriesData.values().next().value?.value ?? 0,
          params.time,
          candleSeries as any,
        );
      } catch {}
    };
    priceChart.subscribeCrosshairMove(syncHandler);
    volChart.subscribeCrosshairMove(syncHandlerVol);

    // ── ResizeObserver ───────────────────────────────────────────────
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) {
          priceChart.applyOptions({ width });
          volChart.applyOptions({ width });
        }
      }
    });
    if (priceRef.current) ro.observe(priceRef.current);

    return () => {
      ro.disconnect();
      try { priceChart.unsubscribeCrosshairMove(syncHandler); } catch {}
      try { volChart.unsubscribeCrosshairMove(syncHandlerVol); } catch {}
      try { priceChart.remove(); } catch {}
      try { volChart.remove(); } catch {}
      priceChartRef.current = null;
      volChartRef.current = null;
    };
  }, [priceSeries, volumeSeries, markers, priceHeight, volHeight, srLevels]);

  return (
    <div style={{ width: '100%' }}>
      {/* S/R legend */}
      {srLevels.length > 0 && (
        <div className="flex items-center gap-3 mb-1 px-1">
          <span className="text-[10px] text-gray-500">Levels:</span>
          {srLevels.map((lvl, i) => (
            <span key={i} className="text-[10px] font-mono" style={{ color: lvl.type === 'resistance' ? '#ef4444' : '#22c55e' }}>
              {lvl.type === 'resistance' ? 'R' : 'S'} {lvl.price.toFixed(2)}
            </span>
          ))}
        </div>
      )}
      <div ref={priceRef} style={{ width: '100%', height: priceHeight, overflow: 'hidden' }} />
      <div style={{ height: 1, backgroundColor: '#1f2937' }} />
      <div ref={volRef} style={{ width: '100%', height: volHeight, overflow: 'hidden' }} />
    </div>
  );
};
