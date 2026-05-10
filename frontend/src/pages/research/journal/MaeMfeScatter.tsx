import { useMemo } from 'react'
import { Group } from '@visx/group'
import { scaleLinear } from '@visx/scale'
import { AxisBottom, AxisLeft } from '@visx/axis'
import { GridColumns, GridRows } from '@visx/grid'
import { ParentSize } from '@visx/responsive'
import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { Crosshair } from 'lucide-react'
import type { TradeJournalEntry } from '../useResearchData'

interface MaeMfeScatterProps {
  trades: TradeJournalEntry[] | undefined
  loading?: boolean
}

/**
 * MAE × MFE scatter. Each dot = one trade.
 *   x = max adverse excursion (absolute %, lower is better)
 *   y = max favorable excursion (%, higher is better)
 *   colour = P&L sign
 *
 * A 45° dashed line marks the break-even ratio (|MAE| == MFE). Trades above
 * the line are winners that left money on the table; below the line are
 * trades whose trailing-stop was too tight.
 */
export function MaeMfeScatter({ trades, loading }: MaeMfeScatterProps) {
  const points = useMemo(() => {
    const xs = trades ?? []
    return xs
      .map((t) => {
        const mae = Math.abs(Number(t.max_adverse_excursion ?? NaN))
        const mfe = Math.abs(Number(t.max_favorable_excursion ?? NaN))
        if (!Number.isFinite(mae) || !Number.isFinite(mfe)) return null
        return {
          id: t.id,
          symbol: t.symbol,
          mae,
          mfe,
          pnl: Number(t.pnl ?? 0),
        }
      })
      .filter(
        (p): p is { id: number; symbol: string; mae: number; mfe: number; pnl: number } =>
          p != null,
      )
  }, [trades])

  if (loading && !trades) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>MAE × MFE scatter</SectionLabel>
        <div className="h-[320px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!points.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>MAE × MFE scatter</SectionLabel>
        <EmptyState
          icon={Crosshair}
          title="No MAE/MFE data"
          description="Populates once trade_journal rows have max_adverse_excursion and max_favorable_excursion populated."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>MAE × MFE scatter · {points.length} trades</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <ParentSize debounceTime={50}>
          {({ width }) => (
            <Scatter data={points} width={Math.max(360, width)} height={320} />
          )}
        </ParentSize>
      </div>
    </section>
  )
}

function Scatter({
  data,
  width,
  height,
}: {
  data: Array<{ id: number; symbol: string; mae: number; mfe: number; pnl: number }>
  width: number
  height: number
}) {
  const margin = { top: 8, right: 12, bottom: 32, left: 44 }
  const iw = Math.max(100, width - margin.left - margin.right)
  const ih = Math.max(100, height - margin.top - margin.bottom)

  const maxMae = Math.max(...data.map((d) => d.mae), 1)
  const maxMfe = Math.max(...data.map((d) => d.mfe), 1)
  const lim = Math.max(maxMae, maxMfe) * 1.05

  const xScale = scaleLinear({ domain: [0, lim], range: [0, iw], nice: true })
  const yScale = scaleLinear({ domain: [0, lim], range: [ih, 0], nice: true })

  return (
    <svg width={width} height={height}>
      <Group left={margin.left} top={margin.top}>
        <GridRows scale={yScale} width={iw} stroke="var(--border-subtle)" strokeDasharray="2 4" numTicks={5} />
        <GridColumns scale={xScale} height={ih} stroke="var(--border-subtle)" strokeDasharray="2 4" numTicks={5} />
        <line
          x1={xScale(0)}
          y1={yScale(0)}
          x2={xScale(lim)}
          y2={yScale(lim)}
          stroke="var(--text-3)"
          strokeDasharray="3 3"
          strokeWidth={1}
        />
        {data.map((d) => (
          <circle
            key={d.id}
            cx={xScale(d.mae)}
            cy={yScale(d.mfe)}
            r={3}
            fill={d.pnl >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'}
            fillOpacity={0.7}
            stroke="none"
          >
            <title>
              {d.symbol} — MAE {d.mae.toFixed(2)}% · MFE {d.mfe.toFixed(2)}% · P&L {d.pnl.toFixed(2)}
            </title>
          </circle>
        ))}
        <AxisLeft
          scale={yScale}
          stroke="var(--border-subtle)"
          tickStroke="var(--border-subtle)"
          numTicks={5}
          tickFormat={(v) => `${(v as number).toFixed(1)}%`}
          tickLabelProps={{
            fill: 'var(--text-3)',
            fontSize: 10,
            fontFamily: 'var(--font-mono)',
            textAnchor: 'end',
            dx: -4,
            dy: 3,
          }}
          label="MFE %"
          labelProps={{ fill: 'var(--text-2)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
        />
        <AxisBottom
          top={ih}
          scale={xScale}
          stroke="var(--border-subtle)"
          tickStroke="var(--border-subtle)"
          numTicks={5}
          tickFormat={(v) => `${(v as number).toFixed(1)}%`}
          tickLabelProps={{
            fill: 'var(--text-3)',
            fontSize: 10,
            fontFamily: 'var(--font-mono)',
            textAnchor: 'middle',
          }}
          label="MAE %"
          labelProps={{ fill: 'var(--text-2)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
        />
      </Group>
    </svg>
  )
}
