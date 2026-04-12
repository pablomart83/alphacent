import { type FC, useMemo, useEffect, useRef } from 'react';
import {
  createChart,
  type IChartApi,
  ColorType,
  CrosshairMode,
  LineStyle,
  LineSeries,
  type ISeriesApi,
  type SeriesType,
  createSeriesMarkers,
} from 'lightweight-charts';

export interface PricePoint {
  date: string;
  price: number;
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

const THEME = {
  bg: '#0a0e1a',
  grid: '#1f2937',
  text: '#9ca3af',
  crosshair: '#6b7280',
  line: '#3b82f6',
};

export const AssetPlot: FC<AssetPlotProps> = ({ priceData, orders = [], symbol, height = 300 }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<SeriesType> | null>(null);

  // Sort and deduplicate price data
  const sortedData = useMemo(() => {
    if (!priceData.length) return [];
    const map = new Map<string, number>();
    for (const d of priceData) {
      const key = d.date.slice(0, 10);
      map.set(key, d.price);
    }
    return Array.from(map.entries())
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, price]) => ({ time: date, value: price }));
  }, [priceData]);

  // Build markers from orders
  const markers = useMemo(() => {
    return orders
      .map((o) => ({
        time: o.date.slice(0, 10),
        position: o.side === 'BUY' ? 'belowBar' as const : 'aboveBar' as const,
        color: o.side === 'BUY' ? '#22c55e' : '#ef4444',
        shape: o.side === 'BUY' ? 'arrowUp' as const : 'arrowDown' as const,
        text: o.side === 'BUY' ? 'B' : 'S',
      }))
      .sort((a, b) => a.time.localeCompare(b.time));
  }, [orders]);

  // Create chart
  useEffect(() => {
    if (!containerRef.current || sortedData.length === 0) return;

    const chart = createChart(containerRef.current, {
      width: containerRef.current.clientWidth,
      height,
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
        borderColor: THEME.grid,
        timeVisible: false,
        rightOffset: 5,
      },
      rightPriceScale: {
        borderColor: THEME.grid,
      },
      handleScroll: { mouseWheel: true, pressedMouseMove: true },
      handleScale: { mouseWheel: true, pinch: true },
    });

    chartRef.current = chart;

    // Add line series for price
    const series = chart.addSeries(LineSeries, {
      color: THEME.line,
      lineWidth: 2,
      priceFormat: { type: 'price', precision: 2, minMove: 0.01 },
    });

    series.setData(sortedData as any);
    seriesRef.current = series;

    // Add order markers
    if (markers.length > 0) {
      createSeriesMarkers(series, markers as any);
    }

    chart.timeScale().fitContent();

    // ResizeObserver
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width } = entry.contentRect;
        if (width > 0) chart.applyOptions({ width });
      }
    });
    ro.observe(containerRef.current);

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
    };
  }, [sortedData, markers, height]);

  if (priceData.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ height }}>
        No price data available for {symbol}
      </div>
    );
  }

  return <div ref={containerRef} style={{ width: '100%', height }} />;
};
