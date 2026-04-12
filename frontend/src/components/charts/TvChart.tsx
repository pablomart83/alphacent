import {
  type FC,
  useRef,
  useEffect,
  memo,
  type CSSProperties,
} from 'react';
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

// ── AlphaCent dark theme ─────────────────────────────────────────────────
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
  volume: 'rgba(59, 130, 246, 0.3)',
};

// ── Types ────────────────────────────────────────────────────────────────
export type TvChartType = 'area' | 'line' | 'candlestick' | 'histogram' | 'baseline';

export interface TvSeriesConfig {
  id: string;
  type: TvChartType;
  data: TvDataPoint[];
  color?: string;
  lineWidth?: number;
  topColor?: string;
  bottomColor?: string;
  lineColor?: string;
  baseValue?: number;
  topFillColor1?: string;
  topFillColor2?: string;
  bottomFillColor1?: string;
  bottomFillColor2?: string;
  topLineColor?: string;
  bottomLineColor?: string;
  priceScaleId?: string;
  dashed?: boolean;
}

export interface TvDataPoint {
  time: string | number;
  value?: number;
  open?: number;
  high?: number;
  low?: number;
  close?: number;
  color?: string;
}

export interface TvChartProps {
  series: TvSeriesConfig[];
  height?: number;
  showTimeScale?: boolean;
  showPriceScale?: boolean;
  onCrosshairMove?: (params: MouseEventParams<Time>) => void;
  style?: CSSProperties;
  className?: string;
  autoResize?: boolean;
}

function toChartTime(t: string | number): Time {
  if (typeof t === 'number') return t as Time;
  const s = String(t);
  if (s.length === 10) return s as Time;
  return s.slice(0, 10) as Time;
}

function getSeriesDefinition(type: TvChartType) {
  switch (type) {
    case 'area': return AreaSeries;
    case 'line': return LineSeries;
    case 'candlestick': return CandlestickSeries;
    case 'histogram': return HistogramSeries;
    case 'baseline': return BaselineSeries;
  }
}

function buildSeriesOptions(cfg: TvSeriesConfig): Record<string, unknown> {
  const base: Record<string, unknown> = {};
  if (cfg.priceScaleId) base.priceScaleId = cfg.priceScaleId;

  switch (cfg.type) {
    case 'area':
      return {
        ...base,
        lineColor: cfg.lineColor || cfg.color || THEME.areaLine,
        topColor: cfg.topColor || (cfg.color ? `${cfg.color}33` : THEME.area),
        bottomColor: cfg.bottomColor || 'transparent',
        lineWidth: cfg.lineWidth || 2,
      };
    case 'line':
      return {
        ...base,
        color: cfg.color || THEME.line,
        lineWidth: cfg.lineWidth || 2,
        lineStyle: cfg.dashed ? LineStyle.Dashed : LineStyle.Solid,
      };
    case 'candlestick':
      return {
        ...base,
        upColor: THEME.up,
        downColor: THEME.down,
        borderUpColor: THEME.up,
        borderDownColor: THEME.down,
        wickUpColor: THEME.up,
        wickDownColor: THEME.down,
      };
    case 'histogram':
      return {
        ...base,
        color: cfg.color || THEME.volume,
        priceFormat: { type: 'volume' as const },
        priceScaleId: cfg.priceScaleId || 'volume',
      };
    case 'baseline':
      return {
        ...base,
        baseValue: { type: 'price' as const, price: cfg.baseValue ?? 0 },
        topFillColor1: cfg.topFillColor1 || 'rgba(34, 197, 94, 0.2)',
        topFillColor2: cfg.topFillColor2 || 'rgba(34, 197, 94, 0.02)',
        bottomFillColor1: cfg.bottomFillColor1 || 'rgba(239, 68, 68, 0.02)',
        bottomFillColor2: cfg.bottomFillColor2 || 'rgba(239, 68, 68, 0.2)',
        topLineColor: cfg.topLineColor || THEME.up,
        bottomLineColor: cfg.bottomLineColor || THEME.down,
        lineWidth: cfg.lineWidth || 2,
      };
    default:
      return base;
  }
}

const TvChartInner: FC<TvChartProps> = ({
  series,
  height = 300,
  showTimeScale = true,
  showPriceScale = true,
  onCrosshairMove,
  style,
  className,
  autoResize = true,
}) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesMapRef = useRef<Map<string, ISeriesApi<SeriesType>>>(new Map());

  // Create chart on mount
  useEffect(() => {
    if (!containerRef.current) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
      layout: {
        background: { type: ColorType.Solid, color: THEME.bg },
        textColor: THEME.text,
        fontFamily: "'JetBrains Mono', 'Courier New', monospace",
        fontSize: 11,
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
        visible: showTimeScale,
        borderColor: THEME.grid,
        timeVisible: false,
        rightOffset: 5,
        barSpacing: 6,
      },
      rightPriceScale: {
        visible: showPriceScale,
        borderColor: THEME.grid,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    let ro: ResizeObserver | null = null;
    if (autoResize) {
      ro = new ResizeObserver((entries) => {
        for (const entry of entries) {
          const { width } = entry.contentRect;
          if (width > 0) chart.applyOptions({ width });
        }
      });
      ro.observe(containerRef.current);
    }

    return () => {
      ro?.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesMapRef.current.clear();
    };
  }, [height, showTimeScale, showPriceScale, autoResize]);

  // Crosshair callback
  useEffect(() => {
    if (!chartRef.current || !onCrosshairMove) return;
    chartRef.current.subscribeCrosshairMove(onCrosshairMove);
    return () => {
      chartRef.current?.unsubscribeCrosshairMove(onCrosshairMove);
    };
  }, [onCrosshairMove]);

  // Update series data
  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const existingIds = new Set(seriesMapRef.current.keys());
    const newIds = new Set(series.map((s) => s.id));

    // Remove series that no longer exist
    for (const id of existingIds) {
      if (!newIds.has(id)) {
        const s = seriesMapRef.current.get(id);
        if (s) chart.removeSeries(s);
        seriesMapRef.current.delete(id);
      }
    }

    // Add or update series
    for (const cfg of series) {
      let s = seriesMapRef.current.get(cfg.id);
      const opts = buildSeriesOptions(cfg);
      const def = getSeriesDefinition(cfg.type);

      if (!s) {
        s = chart.addSeries(def, opts as any);
        seriesMapRef.current.set(cfg.id, s);

        // Volume scale margins
        if (cfg.type === 'histogram' && (cfg.priceScaleId === 'volume' || !cfg.priceScaleId)) {
          chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
          });
        }
      } else {
        s.applyOptions(opts as any);
      }

      // Set data
      if (cfg.data.length > 0) {
        const chartData = cfg.data.map((d) => {
          const t = toChartTime(d.time);
          if (cfg.type === 'candlestick') {
            return { time: t, open: d.open ?? 0, high: d.high ?? 0, low: d.low ?? 0, close: d.close ?? 0 };
          }
          if (cfg.type === 'histogram') {
            return { time: t, value: d.value ?? d.close ?? 0, color: d.color };
          }
          return { time: t, value: d.value ?? d.close ?? 0 };
        });

        chartData.sort((a, b) => {
          const ta = typeof a.time === 'string' ? a.time : String(a.time);
          const tb = typeof b.time === 'string' ? b.time : String(b.time);
          return ta.localeCompare(tb);
        });

        s.setData(chartData as any);
      }
    }

    chart.timeScale().fitContent();
  }, [series]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{ width: '100%', height, ...style }}
    />
  );
};

export const TvChart = memo(TvChartInner);
