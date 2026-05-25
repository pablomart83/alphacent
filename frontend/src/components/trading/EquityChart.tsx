import { useEffect, useMemo, useRef, useState } from 'react'
import {
  AreaSeries,
  ColorType,
  CrosshairMode,
  LineSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type AreaData,
  type UTCTimestamp,
  type MouseEventParams,
} from 'lightweight-charts'
import { cn, formatCurrency, formatPercentage, formatTimestamp, parseUtcIso } from '@/lib/utils'
import { Button } from '@/components/primitives'
import { Maximize2, Minimize2 } from 'lucide-react'

export type EquityPeriod = '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL'
export type EquityInterval = '1d' | '4h' | '1h'

export interface EquityPoint {
  /** Either a `YYYY-MM-DD` day string, or a Unix timestamp (seconds, string or number). */
  date: string | number
  equity: number
  /** Optional realised P&L cumulative — plotted as dashed overlay if showRealized. */
  realized?: number | null
}

export interface DrawdownPoint {
  date: string | number
  drawdown_pct: number
}

export interface BenchmarkPoint {
  date: string // YYYY-MM-DD
  close: number
}

interface EquityChartProps {
  equityData: EquityPoint[]
  spyData?: BenchmarkPoint[]
  drawdownData?: DrawdownPoint[]
  period: EquityPeriod
  onPeriodChange: (p: EquityPeriod) => void
  interval: EquityInterval
  onIntervalChange: (iv: EquityInterval) => void
  showBenchmark?: boolean
  onShowBenchmarkChange?: (v: boolean) => void
  showRealized?: boolean
  onShowRealizedChange?: (v: boolean) => void
  showDrawdown?: boolean
  onShowDrawdownChange?: (v: boolean) => void
  /**
   * When true the equity (and realised) series are rebased to % return from
   * the first point so LIVE (flat) vs DEMO (growing) are directly comparable
   * on the same axis. SPY is also rebased to % so the overlay is meaningful.
   */
  percentMode?: boolean
  onPercentModeChange?: (v: boolean) => void
  fullscreen?: boolean
  onFullscreenToggle?: () => void
  /** Loading state — render empty chart shell. */
  loading?: boolean
  className?: string
  /**
   * Fixed inception bases for alpha calculation in the hover legend.
   * These are the ALL-period first points and must NOT change when the user
   * switches the view period (1W/1M/3M). Without them, "Alpha vs SPY" on a
   * given date changes depending on which period is selected because the
   * rebasing origin shifts. With them, alpha is always "return since inception
   * minus SPY return since inception" — period-independent.
   *
   * If not provided, falls back to the first point of the current equityData /
   * spyData (old behaviour — period-relative alpha).
   */
  inceptionEquityBase?: number
  inceptionSpyBase?: number
}

const PERIODS: EquityPeriod[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const INTERVALS: EquityInterval[] = ['1d', '4h', '1h']

function toChartTime(date: string | number): UTCTimestamp | string {
  // Integer / numeric string → treat as unix seconds.
  if (typeof date === 'number') return date as UTCTimestamp
  if (/^\d+$/.test(date)) return Number(date) as UTCTimestamp
  // Otherwise assume YYYY-MM-DD.
  return date
}

function resolveVar(name: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  return v || fallback
}

export function EquityChart({
  equityData,
  spyData,
  drawdownData,
  period,
  onPeriodChange,
  interval,
  onIntervalChange,
  showBenchmark = false,
  onShowBenchmarkChange,
  showRealized = true,
  onShowRealizedChange,
  showDrawdown = true,
  onShowDrawdownChange,
  percentMode = false,
  onPercentModeChange,
  fullscreen = false,
  onFullscreenToggle,
  loading = false,
  className,
  inceptionEquityBase,
  inceptionSpyBase,
}: EquityChartProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const equitySeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const realizedSeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const spySeriesRef = useRef<ISeriesApi<'Line'> | null>(null)
  const drawdownSeriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  // Refs for values read inside the crosshair handler (created once on mount,
  // so it can't close over changing props directly).
  const percentModeRef = useRef(percentMode)
  const equityDataRef = useRef(equityData)
  const spyDataRef = useRef(spyData)
  // Inception bases for period-independent alpha calculation in the hover legend.
  const inceptionEquityBaseRef = useRef(inceptionEquityBase)
  const inceptionSpyBaseRef = useRef(inceptionSpyBase)
  useEffect(() => { percentModeRef.current = percentMode }, [percentMode])
  useEffect(() => { equityDataRef.current = equityData }, [equityData])
  useEffect(() => { spyDataRef.current = spyData }, [spyData])
  useEffect(() => { inceptionEquityBaseRef.current = inceptionEquityBase }, [inceptionEquityBase])
  useEffect(() => { inceptionSpyBaseRef.current = inceptionSpyBase }, [inceptionSpyBase])

  const [hover, setHover] = useState<{
    time: string | null
    equity: number | null
    realized: number | null
    realizedAlphaSpy: number | null
    drawdown: number | null
    spyAlpha: number | null
  } | null>(null)

  // Build and tear down the chart on mount.
  useEffect(() => {
    const el = containerRef.current
    if (!el) return

    const chart = createChart(el, {
      layout: {
        background: { type: ColorType.Solid, color: resolveVar('--bg-1', '#101012') },
        textColor: resolveVar('--text-2', '#8a8e99'),
        fontSize: 11,
        fontFamily:
          "'Inter Variable', system-ui, -apple-system, 'Segoe UI', sans-serif",
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
      rightPriceScale: {
        borderColor: resolveVar('--border-subtle', '#1f2024'),
      },
      timeScale: {
        borderColor: resolveVar('--border-subtle', '#1f2024'),
        timeVisible: true,
        secondsVisible: false,
      },
      autoSize: true,
    })

    const equitySeries = chart.addSeries(
      LineSeries,
      {
        color: resolveVar('--accent-primary', '#3b82f6'),
        lineWidth: 2,
        priceFormat: { type: 'price', precision: 0, minMove: 1 },
      },
      0,
    )

    chartRef.current = chart
    equitySeriesRef.current = equitySeries

    const subscribe = (param: MouseEventParams) => {
      if (!param.time || !param.point) {
        setHover(null)
        return
      }
      const eqData = param.seriesData.get(equitySeries) as LineData | undefined
      const realizedData = realizedSeriesRef.current
        ? (param.seriesData.get(realizedSeriesRef.current) as LineData | undefined)
        : undefined
      const ddData = drawdownSeriesRef.current
        ? (param.seriesData.get(drawdownSeriesRef.current) as AreaData | undefined)
        : undefined
      const spyPoint = spySeriesRef.current
        ? (param.seriesData.get(spySeriesRef.current) as LineData | undefined)
        : undefined

      const timeStr = typeof param.time === 'number'
        ? new Date((param.time as number) * 1000).toISOString()
        : String(param.time)

      // Alpha vs SPY.
      // The SPY series is stored differently depending on display mode:
      //   percent mode: spyVal = ((close - spyBase) / spyBase) * 100  — already a % return
      //   dollar mode:  spyVal = eqBase * (close / spyBase)           — rebased to equity dollars
      //
      // IMPORTANT: alpha in the hover legend must be period-independent.
      // We use inceptionEquityBase / inceptionSpyBase (ALL-period first points)
      // so that "Alpha vs SPY" on a given date doesn't change when the user
      // switches the view period. The visual series rebasing stays period-relative
      // (correct for the chart lines); only the legend numbers use inception bases.
      //
      // Fallback: if inception bases aren't provided, use the current period's
      // first point (old behaviour — period-relative alpha).
      let spyAlpha: number | null = null
      if (spyPoint && eqData) {
        const eqVal = eqData.value as number
        const spyVal = spyPoint.value as number
        if (Number.isFinite(eqVal) && Number.isFinite(spyVal)) {
          if (percentModeRef.current) {
            // Both series already in % from their respective first points.
            // In percent mode the series are rebased to the period start, so
            // direct subtraction gives period-relative alpha. To get
            // inception-relative alpha we'd need to re-derive from raw prices —
            // not available here. Accept period-relative alpha in percent mode.
            spyAlpha = eqVal - spyVal
          } else {
            // Dollar mode: eqVal is raw equity $; spyVal is rebased to the
            // period's eqBase. Use inception bases for period-independent alpha.
            const eqBase = inceptionEquityBaseRef.current ?? equityDataRef.current[0]?.equity
            const periodEqBase = equityDataRef.current[0]?.equity  // period start (for SPY rebasing)
            const periodSpyBase = spyDataRef.current?.[0]?.close   // SPY at period start
            if (eqBase && eqBase > 0 && periodEqBase && periodEqBase > 0 && periodSpyBase && periodSpyBase > 0) {
              // eqVal is raw equity — compute return from inception
              const eqRet = ((eqVal - eqBase) / eqBase) * 100
              // spyVal is rebased to periodEqBase: spyVal = periodEqBase * (spyClose / periodSpyBase)
              // Recover raw SPY close: spyClose = spyVal * periodSpyBase / periodEqBase
              const spyClose = spyVal * periodSpyBase / periodEqBase
              // Compute SPY return from inception SPY base
              const inceptionSpyB = inceptionSpyBaseRef.current ?? periodSpyBase
              const spyRet = ((spyClose - inceptionSpyB) / inceptionSpyB) * 100
              spyAlpha = eqRet - spyRet
            }
          }
        }
      }

      setHover({
        time: timeStr,
        equity: eqData ? (eqData.value as number) : null,
        realized: realizedData ? (realizedData.value as number) : null,
        realizedAlphaSpy: (() => {
          // Alpha Realised vs SPY: realized return % minus SPY return % at this point.
          // Uses inception bases for period-independent numbers (same logic as spyAlpha above).
          if (!realizedData || !spyPoint) return null
          const realVal = realizedData.value as number
          const spyVal = spyPoint.value as number
          if (!Number.isFinite(realVal) || !Number.isFinite(spyVal)) return null
          if (percentModeRef.current) {
            return realVal - spyVal
          }
          const eqBase = inceptionEquityBaseRef.current ?? equityDataRef.current[0]?.equity
          const periodEqBase = equityDataRef.current[0]?.equity
          const periodSpyBase = spyDataRef.current?.[0]?.close
          if (!eqBase || !periodEqBase || !periodSpyBase || eqBase <= 0 || periodEqBase <= 0 || periodSpyBase <= 0) return null
          // realized is cumulative realized P&L in $; compute as % of inception equity
          const realPct = (realVal / eqBase) * 100
          // recover raw SPY close from rebased value, then compute from inception SPY base
          const spyClose = spyVal * periodSpyBase / periodEqBase
          const inceptionSpyB = inceptionSpyBaseRef.current ?? periodSpyBase
          const spyPct = ((spyClose - inceptionSpyB) / inceptionSpyB) * 100
          return realPct - spyPct
        })(),
        drawdown: ddData ? (ddData.value as number) : null,
        spyAlpha,
      })
    }

    chart.subscribeCrosshairMove(subscribe)

    return () => {
      chart.unsubscribeCrosshairMove(subscribe)
      chart.remove()
      chartRef.current = null
      equitySeriesRef.current = null
      realizedSeriesRef.current = null
      spySeriesRef.current = null
      drawdownSeriesRef.current = null
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // Equity + realized line data.
  useEffect(() => {
    const equitySeries = equitySeriesRef.current
    if (!equitySeries) return
    if (!equityData || equityData.length === 0) {
      equitySeries.setData([])
      // Clear realized series too — no data means no realized line.
      if (realizedSeriesRef.current) {
        chartRef.current?.removeSeries(realizedSeriesRef.current)
        realizedSeriesRef.current = null
      }
      return
    }

    // Dedup + sort by time. LWC requires monotonically increasing time.
    const seen = new Map<string | number, EquityPoint>()
    for (const p of equityData) {
      const t = toChartTime(p.date)
      seen.set(t as any, p)
    }
    const ordered = Array.from(seen.entries())
      .map(([t, p]) => ({ time: t as any, value: Number(p.equity), realized: p.realized }))
      .filter((d) => Number.isFinite(d.value) && d.value > 0)
      .sort((a, b) =>
        typeof a.time === 'number'
          ? (a.time as number) - (b.time as number)
          : String(a.time).localeCompare(String(b.time)),
      )

    if (ordered.length === 0) {
      equitySeries.setData([])
      if (realizedSeriesRef.current) {
        chartRef.current?.removeSeries(realizedSeriesRef.current)
        realizedSeriesRef.current = null
      }
      return
    }

    // Base equity value for % rebasing — always the first valid equity point.
    const eqBase = ordered[0].value

    // In percent mode: equity % return from first point.
    // In dollar mode: raw equity value.
    const toEquityDisplay = (v: number) =>
      percentMode ? ((v - eqBase) / eqBase) * 100 : v

    // Update price format to match mode.
    equitySeries.applyOptions(
      percentMode
        ? { priceFormat: { type: 'percent', precision: 2, minMove: 0.01 } }
        : { priceFormat: { type: 'price', precision: 0, minMove: 1 } },
    )

    equitySeries.setData(ordered.map((d) => ({ time: d.time, value: toEquityDisplay(d.value) })))

    // Realized cumulative overlay.
    // In percent mode: realized P&L as % of starting equity (same denominator as equity line).
    //   → gap between equity line and realized line = unrealized P&L as % of starting equity.
    // In dollar mode: raw realized_pnl_cumulative value.
    // Guard: skip if realized values are all zero/null (no closed trades yet).
    if (showRealized) {
      const realizedPoints = ordered.filter(
        (d) => d.realized != null && Number.isFinite(d.realized as number),
      )
      const hasRealized = realizedPoints.length > 0 && realizedPoints.some((d) => (d.realized as number) !== 0)

      if (hasRealized) {
        if (!realizedSeriesRef.current) {
          realizedSeriesRef.current = chartRef.current!.addSeries(
            LineSeries,
            {
              color: resolveVar('--text-2', '#8a8e99'),
              lineWidth: 1,
              lineStyle: LineStyle.Dashed,
              priceLineVisible: false,
              lastValueVisible: false,
            },
            0,
          )
        }
        realizedSeriesRef.current!.applyOptions(
          percentMode
            ? { priceFormat: { type: 'percent', precision: 2, minMove: 0.01 } }
            : { priceFormat: { type: 'price', precision: 0, minMove: 1 } },
        )
        // realized as % of starting equity (eqBase), not % of its own first value.
        const toRealizedDisplay = (rv: number) =>
          percentMode && eqBase > 0 ? (rv / eqBase) * 100 : rv

        realizedSeriesRef.current!.setData(
          realizedPoints.map((d) => ({
            time: d.time,
            value: toRealizedDisplay(d.realized as number),
          })),
        )
      } else {
        // No realized data — remove the series if it exists from a previous mode.
        if (realizedSeriesRef.current) {
          chartRef.current?.removeSeries(realizedSeriesRef.current)
          realizedSeriesRef.current = null
        }
      }
    } else {
      if (realizedSeriesRef.current) {
        chartRef.current?.removeSeries(realizedSeriesRef.current)
        realizedSeriesRef.current = null
      }
    }

    chartRef.current?.timeScale().fitContent()
  }, [equityData, showRealized, percentMode])

  // SPY benchmark overlay — rebased to equity start so the line is comparable.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    if (!showBenchmark || !spyData || spyData.length === 0 || equityData.length === 0) {
      if (spySeriesRef.current) {
        chart.removeSeries(spySeriesRef.current)
        spySeriesRef.current = null
      }
      return
    }

    const spyBase = Number(spyData[0].close)
    if (!Number.isFinite(spyBase) || spyBase <= 0) return

    // In percent mode: show SPY as % return from its own first point (same axis as equity %).
    // In dollar mode: rebase SPY to equity start value so the lines are visually comparable.
    const eqBase = Number(equityData[0].equity)
    if (!percentMode && (!Number.isFinite(eqBase) || eqBase <= 0)) return

    // Dedup by time and enforce monotonically increasing order — LWC throws
    // inside requestAnimationFrame if any point has a null/NaN value or if
    // two points share the same time.
    const seen = new Map<string | number, number>()
    for (const p of spyData) {
      const close = Number(p.close)
      if (!Number.isFinite(close) || close <= 0) continue
      const t = toChartTime(p.date)
      const v = percentMode
        ? ((close - spyBase) / spyBase) * 100
        : eqBase * (close / spyBase)
      if (!Number.isFinite(v)) continue
      seen.set(t as any, v)
    }
    const rebased: LineData[] = Array.from(seen.entries())
      .map(([t, v]) => ({ time: t as any, value: v }))
      .sort((a, b) =>
        typeof a.time === 'number'
          ? (a.time as number) - (b.time as number)
          : String(a.time).localeCompare(String(b.time)),
      )

    if (rebased.length === 0) {
      if (spySeriesRef.current) {
        chart.removeSeries(spySeriesRef.current)
        spySeriesRef.current = null
      }
      return
    }

    if (!spySeriesRef.current) {
      spySeriesRef.current = chart.addSeries(
        LineSeries,
        {
          color: resolveVar('--status-warning', '#f59e0b'),
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
        },
        0,
      )
    }
    spySeriesRef.current!.applyOptions(
      percentMode
        ? { priceFormat: { type: 'percent', precision: 2, minMove: 0.01 } }
        : { priceFormat: { type: 'price', precision: 0, minMove: 1 } },
    )
    spySeriesRef.current!.setData(rebased)
  }, [spyData, showBenchmark, equityData, percentMode])

  // Drawdown pane (separate pane 1 — 30% stretch).
  // Values must be ≤ 0 for the area to fill downward from the zero baseline.
  // The backend emits positive drawdown_pct (e.g. 5.2 = 5.2% drawdown).
  // We negate here so LWC renders the area below zero.
  useEffect(() => {
    const chart = chartRef.current
    if (!chart) return

    if (!showDrawdown || !drawdownData || drawdownData.length === 0) {
      if (drawdownSeriesRef.current) {
        chart.removeSeries(drawdownSeriesRef.current)
        drawdownSeriesRef.current = null
      }
      return
    }

    if (!drawdownSeriesRef.current) {
      drawdownSeriesRef.current = chart.addSeries(
        AreaSeries,
        {
          lineColor: resolveVar('--pnl-down', '#ef4444'),
          topColor: 'rgba(239, 68, 68, 0.0)',
          bottomColor: 'rgba(239, 68, 68, 0.35)',
          lineWidth: 1,
          priceLineVisible: false,
          lastValueVisible: false,
          priceFormat: { type: 'percent', precision: 2, minMove: 0.01 },
        },
        1,
      )
      const panes = chart.panes()
      if (panes.length > 1) panes[1].setStretchFactor(0.35)
    }

    // Dedup + sort to satisfy LWC's monotonically-increasing-time invariant.
    // Negate so values are ≤ 0 (area fills downward from 0 baseline).
    const seen = new Map<string | number, number>()
    for (const d of drawdownData) {
      const v = Number(d.drawdown_pct)
      if (!Number.isFinite(v)) continue
      const t = toChartTime(d.date)
      seen.set(t as any, -Math.abs(v))  // always negative
    }
    const data: AreaData[] = Array.from(seen.entries())
      .map(([t, v]) => ({ time: t as any, value: v }))
      .sort((a, b) =>
        typeof a.time === 'number'
          ? (a.time as number) - (b.time as number)
          : String(a.time).localeCompare(String(b.time)),
      )

    drawdownSeriesRef.current!.setData(data)
  }, [drawdownData, showDrawdown])

  const hoverReadout = useMemo(() => {
    if (!hover || !hover.equity) return null
    const tsLabel = hover.time ? formatTimestamp(parseUtcIso(hover.time), 'short') : '—'
    return (
      <div className="absolute top-2 right-2 z-10 bg-[var(--bg-2)]/95 backdrop-blur rounded-[3px] border border-[var(--border-default)] px-2 py-1.5 pointer-events-none">
        <div className="flex flex-col gap-0.5 text-[10px]">
          <div className="text-[var(--text-3)] uppercase tracking-wide">{tsLabel}</div>
          <div className="flex items-center gap-2 mono">
            <span className="text-[var(--text-2)]">
              {percentMode ? 'Return' : 'Equity'}
            </span>
            <span className="text-[var(--text-0)] font-semibold">
              {percentMode
                ? formatPercentage(hover.equity, { precision: 2, signed: true })
                : formatCurrency(hover.equity, { precision: 0 })}
            </span>
          </div>
          {hover.realized != null && showRealized && (
            <div className="flex items-center gap-2 mono">
              <span className="text-[var(--text-2)]">Realised</span>
              <span className="text-[var(--text-1)]">
                {percentMode
                  ? formatPercentage(hover.realized, { precision: 2, signed: true })
                  : formatCurrency(hover.realized, { precision: 0 })}
              </span>
            </div>
          )}
          {hover.realizedAlphaSpy != null && showRealized && showBenchmark && (
            <div className="flex items-center gap-2 mono">
              <span className="text-[var(--text-2)]">Realised α SPY</span>
              <span style={{ color: hover.realizedAlphaSpy >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)' }}>
                {formatPercentage(hover.realizedAlphaSpy, { precision: 2, signed: true })}
              </span>
            </div>
          )}
          {hover.drawdown != null && (
            <div className="flex items-center gap-2 mono">
              <span className="text-[var(--text-2)]">Drawdown</span>
              <span className="text-[var(--pnl-down)]">
                {formatPercentage(hover.drawdown, { precision: 2, signed: false })}
              </span>
            </div>
          )}
          {hover.spyAlpha != null && (
            <div className="flex items-center gap-2 mono">
              <span className="text-[var(--text-2)]">Alpha vs SPY</span>
              <span
                style={{
                  color:
                    hover.spyAlpha >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)',
                }}
              >
                {formatPercentage(hover.spyAlpha, { precision: 2, signed: true })}
              </span>
            </div>
          )}
        </div>
      </div>
    )
  }, [hover, percentMode, showRealized])

  return (
    <div className={cn('flex flex-col h-full min-h-0', className)}>
      {/* Toolbar */}
      <div className="flex items-center justify-between px-2 py-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0">
        <div className="flex items-center gap-1">
          <SegmentedControl
            label="Period"
            options={PERIODS}
            value={period}
            onChange={onPeriodChange}
          />
          <span className="w-px h-4 bg-[var(--border-subtle)] mx-1" />
          <SegmentedControl
            label="Interval"
            options={INTERVALS}
            value={interval}
            onChange={onIntervalChange}
          />
        </div>
        <div className="flex items-center gap-1">
          {onShowBenchmarkChange && (
            <ToggleChip
              label="SPY"
              active={showBenchmark}
              onClick={() => onShowBenchmarkChange(!showBenchmark)}
            />
          )}
          {onShowRealizedChange && (
            <ToggleChip
              label="Realised"
              active={showRealized}
              onClick={() => onShowRealizedChange(!showRealized)}
            />
          )}
          {onShowDrawdownChange && (
            <ToggleChip
              label="Drawdown"
              active={showDrawdown}
              onClick={() => onShowDrawdownChange(!showDrawdown)}
            />
          )}
          {onPercentModeChange && (
            <ToggleChip
              label="%"
              active={percentMode}
              onClick={() => onPercentModeChange(!percentMode)}
              title="Switch y-axis to % return (rebased from first point)"
            />
          )}
          {onFullscreenToggle && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={onFullscreenToggle}
              aria-label={fullscreen ? 'Exit fullscreen' : 'Fullscreen chart'}
              title="Fullscreen (F)"
            >
              {fullscreen ? (
                <Minimize2 className="h-3.5 w-3.5" />
              ) : (
                <Maximize2 className="h-3.5 w-3.5" />
              )}
            </Button>
          )}
        </div>
      </div>

      {/* Chart body */}
      <div className="relative flex-1 min-h-0">
        {loading && equityData.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-[11px] text-[var(--text-3)]">
            Loading equity curve…
          </div>
        )}
        {!loading && equityData.length === 0 && (
          <div className="absolute inset-0 flex items-center justify-center text-[11px] text-[var(--text-3)]">
            No equity history yet. Snapshots populate as the account trades.
          </div>
        )}
        <div ref={containerRef} className="absolute inset-0" />
        {hoverReadout}
      </div>
    </div>
  )
}

function SegmentedControl<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string
  options: readonly T[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div role="radiogroup" aria-label={label} className="inline-flex gap-0.5">
      {options.map((o) => {
        const active = o === value
        return (
          <button
            key={o}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => onChange(o)}
            className={cn(
              'h-6 px-2 rounded-[2px] text-[10px] font-medium uppercase tracking-wide transition-colors',
              active
                ? 'bg-[var(--bg-active)] text-[var(--text-0)]'
                : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
            )}
          >
            {o}
          </button>
        )
      })}
    </div>
  )
}

function ToggleChip({
  label,
  active,
  onClick,
  title,
}: {
  label: string
  active: boolean
  onClick: () => void
  title?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title={title}
      className={cn(
        'h-6 px-2 rounded-[2px] text-[10px] font-medium uppercase tracking-wide transition-colors',
        active
          ? 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)] text-[var(--accent-primary)]'
          : 'text-[var(--text-3)] hover:text-[var(--text-1)] hover:bg-[var(--bg-hover)]',
      )}
    >
      {label}
    </button>
  )
}
