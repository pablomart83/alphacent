import { useEffect, useMemo, useRef, useState } from 'react'
import {
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  LineStyle,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type UTCTimestamp,
  type SeriesMarker,
  type Time,
} from 'lightweight-charts'
import { cn } from '@/lib/utils'

export interface OHLCVPoint {
  date: string // either YYYY-MM-DD or ISO datetime
  open: number
  high: number
  low: number
  close: number
  volume?: number
}

export interface PriceChartSignal {
  timestamp: string // ISO or YYYY-MM-DD
  type: 'entry' | 'exit' | 'stop' | 'tp' | string
  side?: 'long' | 'short' | 'BUY' | 'SELL' | string
  price: number
  reason?: string
}

export interface PriceChartProps {
  symbol: string
  interval?: '1m' | '5m' | '15m' | '30m' | '1h' | '4h' | '1d'
  bars: OHLCVPoint[]
  signals?: PriceChartSignal[]
  height?: number
  loading?: boolean
  className?: string
}

function resolveVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

function toChartTime(date: string): Time {
  if (/^\d+$/.test(date)) return Number(date) as UTCTimestamp
  if (/^\d{4}-\d{2}-\d{2}$/.test(date)) return date
  // Full ISO → unix seconds.
  const ms = Date.parse(date.endsWith('Z') ? date : `${date}Z`)
  return Math.floor(ms / 1000) as UTCTimestamp
}

export function PriceChart({
  symbol,
  bars,
  signals,
  height,
  loading,
  className,
}: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const markersRef = useRef<ReturnType<typeof createSeriesMarkers<Time>> | null>(null)

  const [hover, setHover] = useState<{ date: string | null; close: number | null } | null>(null)

  // Mount/unmount.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: resolveVar('--bg-1', '#101012') },
        textColor: resolveVar('--text-2', '#8a8e99'),
        fontSize: 11,
        fontFamily: "'Inter Variable', system-ui, sans-serif",
        attributionLogo: false,
      },
      grid: {
        vertLines: { color: resolveVar('--border-subtle', '#1f2024'), style: LineStyle.Dotted },
        horzLines: { color: resolveVar('--border-subtle', '#1f2024'), style: LineStyle.Dotted },
      },
      crosshair: {
        mode: CrosshairMode.Magnet,
        vertLine: { color: resolveVar('--text-3', '#5a5e68'), width: 1 },
        horzLine: { color: resolveVar('--text-3', '#5a5e68'), width: 1 },
      },
      rightPriceScale: { borderColor: resolveVar('--border-subtle', '#1f2024') },
      timeScale: {
        borderColor: resolveVar('--border-subtle', '#1f2024'),
        timeVisible: true,
        secondsVisible: false,
      },
      autoSize: true,
    })

    const series = chart.addSeries(CandlestickSeries, {
      upColor: resolveVar('--pnl-up', '#22c55e'),
      downColor: resolveVar('--pnl-down', '#ef4444'),
      wickUpColor: resolveVar('--pnl-up', '#22c55e'),
      wickDownColor: resolveVar('--pnl-down', '#ef4444'),
      borderVisible: false,
    })

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHover(null)
        return
      }
      const data = param.seriesData.get(series) as CandlestickData | undefined
      setHover({
        date: typeof param.time === 'number'
          ? new Date((param.time as number) * 1000).toISOString().slice(0, 10)
          : String(param.time),
        close: data ? data.close : null,
      })
    })

    chartRef.current = chart
    seriesRef.current = series

    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
      markersRef.current = null
    }
  }, [])

  // Bars.
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return

    const mapped: CandlestickData[] = bars
      .filter((b) => Number.isFinite(b.open) && Number.isFinite(b.close))
      .map((b) => ({
        time: toChartTime(b.date),
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      }))
      .sort((a, b) =>
        typeof a.time === 'number' && typeof b.time === 'number'
          ? a.time - b.time
          : String(a.time).localeCompare(String(b.time)),
      )

    // Dedup same-time bars (keep last).
    const dedup = new Map<string | number, CandlestickData>()
    for (const row of mapped) dedup.set(row.time as any, row)
    series.setData([...dedup.values()])
    chartRef.current?.timeScale().fitContent()
  }, [bars])

  // Signals / markers.
  useEffect(() => {
    const series = seriesRef.current
    if (!series) return
    if (!signals || signals.length === 0) {
      if (markersRef.current) {
        markersRef.current.setMarkers([])
      }
      return
    }

    const markers: SeriesMarker<Time>[] = signals.map((s) => {
      const sideUp = (s.side || '').toUpperCase()
      const isShort = sideUp.includes('SHORT') || sideUp.includes('SELL')
      const typeLower = s.type.toLowerCase()
      const isExit = typeLower.includes('exit') || typeLower.includes('close') || typeLower.includes('stop')

      let color = 'var(--pnl-up)'
      let shape: SeriesMarker<Time>['shape'] = 'arrowUp'
      let position: SeriesMarker<Time>['position'] = 'belowBar'
      let text = s.type.toUpperCase()

      if (typeLower === 'stop') {
        color = resolveVar('--pnl-down', '#ef4444')
        shape = 'circle'
        position = isShort ? 'aboveBar' : 'belowBar'
        text = 'STOP'
      } else if (typeLower === 'tp' || typeLower.includes('profit')) {
        color = resolveVar('--status-warning', '#f59e0b')
        shape = 'square'
        position = isShort ? 'belowBar' : 'aboveBar'
        text = 'TP'
      } else if (isExit) {
        color = isShort ? resolveVar('--pnl-up', '#22c55e') : resolveVar('--pnl-down', '#ef4444')
        shape = 'arrowDown'
        position = 'aboveBar'
        text = 'EXIT'
      } else {
        color = isShort ? resolveVar('--pnl-down', '#ef4444') : resolveVar('--pnl-up', '#22c55e')
        shape = isShort ? 'arrowDown' : 'arrowUp'
        position = isShort ? 'aboveBar' : 'belowBar'
        text = isShort ? 'SELL' : 'BUY'
      }

      return {
        time: toChartTime(s.timestamp),
        position,
        shape,
        color,
        text,
      }
    })

    markers.sort((a, b) =>
      typeof a.time === 'number' && typeof b.time === 'number'
        ? a.time - b.time
        : String(a.time).localeCompare(String(b.time)),
    )

    if (!markersRef.current) {
      markersRef.current = createSeriesMarkers<Time>(series, markers)
    } else {
      markersRef.current.setMarkers(markers)
    }
  }, [signals])

  const hoverReadout = useMemo(() => {
    if (!hover || hover.close == null) return null
    return (
      <div className="absolute top-2 right-2 z-10 bg-[var(--bg-2)]/95 rounded-[3px] border border-[var(--border-default)] px-2 py-1 pointer-events-none">
        <div className="flex flex-col gap-0.5 text-[10px]">
          <span className="text-[var(--text-3)] uppercase tracking-wide">{hover.date}</span>
          <span className="mono text-[var(--text-0)] font-semibold">
            {symbol} {hover.close.toFixed(4)}
          </span>
        </div>
      </div>
    )
  }, [hover, symbol])

  return (
    <div className={cn('relative w-full h-full min-h-[320px]', className)} style={height ? { height } : undefined}>
      {loading && bars.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-[11px] text-[var(--text-3)]">
          Loading chart…
        </div>
      )}
      {!loading && bars.length === 0 && (
        <div className="absolute inset-0 flex items-center justify-center text-[11px] text-[var(--text-3)]">
          No price history available.
        </div>
      )}
      <div ref={containerRef} className="absolute inset-0" />
      {hoverReadout}
    </div>
  )
}
