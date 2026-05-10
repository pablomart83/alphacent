import { useMemo } from 'react'
import { Group } from '@visx/group'
import { scaleLinear, scaleUtc } from '@visx/scale'
import { AreaClosed, LinePath } from '@visx/shape'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { GridRows } from '@visx/grid'
import { ParentSize } from '@visx/responsive'
import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { TrendingDown } from 'lucide-react'
import { parseUtcIso } from '@/lib/utils'
import type { UnderwaterPoint } from '../useResearchData'

interface UnderwaterPlotProps {
  points: UnderwaterPoint[] | undefined
  loading?: boolean
}

export function UnderwaterPlot({ points, loading }: UnderwaterPlotProps) {
  const parsed = useMemo(() => {
    if (!points) return []
    return points
      .map((p) => {
        const d = parseUtcIso(p.date)
        return Number.isNaN(d.getTime())
          ? null
          : { date: d, drawdown: -Math.abs(p.drawdown_pct) }
      })
      .filter(
        (p): p is { date: Date; drawdown: number } => p != null,
      )
      .sort((a, b) => a.date.getTime() - b.date.getTime())
  }, [points])

  if (loading && !points) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Underwater plot</SectionLabel>
        <div className="h-[260px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!parsed.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Underwater plot</SectionLabel>
        <EmptyState
          icon={TrendingDown}
          title="No drawdown timeseries"
          description="Populates once equity_snapshots cover at least the selected period."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Underwater plot</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <ParentSize debounceTime={50}>
          {({ width }) => <Plot data={parsed} width={Math.max(400, width)} height={260} />}
        </ParentSize>
      </div>
    </section>
  )
}

function Plot({
  data,
  width,
  height,
}: {
  data: Array<{ date: Date; drawdown: number }>
  width: number
  height: number
}) {
  const margin = { top: 8, right: 10, bottom: 22, left: 42 }
  const iw = Math.max(80, width - margin.left - margin.right)
  const ih = Math.max(80, height - margin.top - margin.bottom)

  const xScale = scaleUtc<number>({
    domain: [data[0].date, data[data.length - 1].date],
    range: [0, iw],
  })
  const minDd = Math.min(...data.map((d) => d.drawdown))
  const yScale = scaleLinear<number>({
    domain: [Math.min(-1, minDd * 1.05), 0],
    range: [ih, 0],
    nice: true,
  })

  return (
    <svg width={width} height={height}>
      <Group left={margin.left} top={margin.top}>
        <GridRows
          scale={yScale}
          width={iw}
          stroke="var(--border-subtle)"
          strokeDasharray="2 4"
          numTicks={4}
        />
        <AreaClosed
          data={data}
          x={(d) => xScale(d.date) ?? 0}
          y={(d) => yScale(d.drawdown) ?? 0}
          yScale={yScale}
          fill="color-mix(in oklab, var(--pnl-down) 40%, transparent)"
          stroke="none"
        />
        <LinePath
          data={data}
          x={(d) => xScale(d.date) ?? 0}
          y={(d) => yScale(d.drawdown) ?? 0}
          stroke="var(--pnl-down)"
          strokeWidth={1.2}
        />
        <AxisBottom
          top={ih}
          scale={xScale}
          stroke="var(--border-subtle)"
          tickStroke="var(--border-subtle)"
          numTicks={6}
          tickLabelProps={{
            fill: 'var(--text-3)',
            fontSize: 10,
            fontFamily: 'var(--font-mono)',
            textAnchor: 'middle',
          }}
        />
        <AxisLeft
          scale={yScale}
          stroke="var(--border-subtle)"
          tickStroke="var(--border-subtle)"
          numTicks={4}
          tickFormat={(v) => `${(v as number).toFixed(0)}%`}
          tickLabelProps={{
            fill: 'var(--text-3)',
            fontSize: 10,
            fontFamily: 'var(--font-mono)',
            textAnchor: 'end',
            dx: -4,
            dy: 3,
          }}
        />
      </Group>
    </svg>
  )
}
