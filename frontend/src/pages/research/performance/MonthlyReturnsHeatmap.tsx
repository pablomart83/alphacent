import { useMemo } from 'react'
import { Group } from '@visx/group'
import { scaleLinear } from '@visx/scale'
import { ParentSize } from '@visx/responsive'
import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { Calendar } from 'lucide-react'
import type { MonthlyReturn } from '../useResearchData'

interface MonthlyReturnsHeatmapProps {
  entries: MonthlyReturn[]
  loading?: boolean
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

export function MonthlyReturnsHeatmap({ entries, loading }: MonthlyReturnsHeatmapProps) {
  const { years, lookup, max } = useMemo(() => {
    if (!entries.length) {
      return { years: [] as number[], lookup: new Map<string, number>(), max: 0 }
    }
    const ys = Array.from(new Set(entries.map((e) => e.year))).sort((a, b) => a - b)
    const lookup = new Map<string, number>()
    let max = 0
    for (const e of entries) {
      lookup.set(`${e.year}-${e.month}`, e.return_pct)
      if (Math.abs(e.return_pct) > max) max = Math.abs(e.return_pct)
    }
    // Clamp max at 0.5% minimum so tiny months still colour in.
    if (max < 0.5) max = 0.5
    return { years: ys, lookup, max }
  }, [entries])

  if (loading && !entries.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Monthly returns</SectionLabel>
        <div className="h-[180px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!years.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Monthly returns</SectionLabel>
        <EmptyState
          icon={Calendar}
          title="No monthly data yet"
          description="A month with at least one daily snapshot is needed to show up in this grid."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="flex items-center gap-2 text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            <LegendSwatch color="var(--pnl-down)" label={`−${max.toFixed(1)}%`} />
            <LegendSwatch color="var(--bg-2)" label="0" />
            <LegendSwatch color="var(--pnl-up)" label={`+${max.toFixed(1)}%`} />
          </span>
        }
      >
        Monthly returns
      </SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <ParentSize debounceTime={50}>
          {({ width }) => (
            <HeatmapSvg
              years={years}
              lookup={lookup}
              max={max}
              width={Math.max(360, width)}
            />
          )}
        </ParentSize>
      </div>
    </section>
  )
}

function HeatmapSvg({
  years,
  lookup,
  max,
  width,
}: {
  years: number[]
  lookup: Map<string, number>
  max: number
  width: number
}) {
  const axisSize = 50
  const innerW = Math.max(180, width - axisSize - 4)
  const cellW = Math.max(22, innerW / 12)
  const cellH = 22
  const height = axisSize + cellH * years.length + 4

  const colorScale = scaleLinear<string>({
    domain: [-max, 0, max],
    range: ['rgba(239,68,68,0.95)', 'rgba(60,70,90,0.35)', 'rgba(34,197,94,0.95)'],
  })

  return (
    <svg width={width} height={height}>
      <Group left={axisSize}>
        {MONTHS.map((m, i) => (
          <text
            key={m}
            x={i * cellW + cellW / 2}
            y={axisSize - 10}
            textAnchor="middle"
            fontSize={9}
            fill="var(--text-2)"
            fontFamily="var(--font-mono)"
          >
            {m}
          </text>
        ))}
      </Group>
      <Group top={axisSize}>
        {years.map((y, r) => (
          <text
            key={y}
            x={axisSize - 6}
            y={r * cellH + cellH / 2 + 3}
            textAnchor="end"
            fontSize={10}
            fill="var(--text-2)"
            fontFamily="var(--font-mono)"
          >
            {y}
          </text>
        ))}
      </Group>
      <Group left={axisSize} top={axisSize}>
        {years.map((y, r) =>
          MONTHS.map((_, c) => {
            const key = `${y}-${c + 1}`
            const value = lookup.has(key) ? (lookup.get(key) as number) : null
            const fill = value == null ? 'var(--bg-2)' : colorScale(value)
            const opacity = value == null ? 0.4 : 1
            return (
              <g key={key}>
                <rect
                  x={c * cellW + 1}
                  y={r * cellH + 1}
                  width={cellW - 2}
                  height={cellH - 2}
                  fill={fill}
                  opacity={opacity}
                >
                  <title>
                    {value == null
                      ? `${MONTHS[c]} ${y} — no data`
                      : `${MONTHS[c]} ${y} — ${value > 0 ? '+' : ''}${value.toFixed(2)}%`}
                  </title>
                </rect>
                {value != null && Math.abs(value) >= 0.5 && (
                  <text
                    x={c * cellW + cellW / 2}
                    y={r * cellH + cellH / 2 + 3}
                    textAnchor="middle"
                    fontSize={9}
                    fontFamily="var(--font-mono)"
                    fill={Math.abs(value) > max * 0.4 ? '#0b0d12' : 'var(--text-0)'}
                  >
                    {value > 0 ? '+' : ''}
                    {value.toFixed(1)}
                  </text>
                )}
              </g>
            )
          }),
        )}
      </Group>
    </svg>
  )
}

function LegendSwatch({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="h-1.5 w-3 rounded-[1px]" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
