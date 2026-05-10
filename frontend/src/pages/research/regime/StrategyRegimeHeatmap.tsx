import { useMemo } from 'react'
import { Group } from '@visx/group'
import { scaleLinear } from '@visx/scale'
import { ParentSize } from '@visx/responsive'
import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { Grid3x3 } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import type { StrategyRegimeRow } from '../useResearchData'

interface StrategyRegimeHeatmapProps {
  rows: StrategyRegimeRow[] | undefined
  loading?: boolean
}

const REGIME_COLS: Array<{ key: keyof StrategyRegimeRow; label: string }> = [
  { key: 'trending_up', label: 'Trending Up' },
  { key: 'trending_down', label: 'Trending Down' },
  { key: 'ranging', label: 'Ranging' },
  { key: 'volatile', label: 'Volatile' },
]

export function StrategyRegimeHeatmap({ rows, loading }: StrategyRegimeHeatmapProps) {
  const { data, max } = useMemo(() => {
    const xs = rows ?? []
    let m = 0
    for (const r of xs) {
      for (const c of REGIME_COLS) {
        const v = Number(r[c.key] ?? 0)
        if (Math.abs(v) > m) m = Math.abs(v)
      }
    }
    if (m < 1) m = 1
    return { data: xs, max: m }
  }, [rows])

  if (loading && !data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Strategy × regime heatmap</SectionLabel>
        <div className="h-[320px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Strategy × regime heatmap</SectionLabel>
        <EmptyState
          icon={Grid3x3}
          title="No strategy-regime data"
          description="Needs strategies with macro_regime metadata and closed positions to populate."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Strategy × regime heatmap · Σ P&L</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <ParentSize debounceTime={50}>
          {({ width }) => (
            <HeatmapSvg data={data} max={max} width={Math.max(360, width)} />
          )}
        </ParentSize>
      </div>
    </section>
  )
}

function HeatmapSvg({
  data,
  max,
  width,
}: {
  data: StrategyRegimeRow[]
  max: number
  width: number
}) {
  const axisSize = 220
  const colCount = REGIME_COLS.length
  const innerW = Math.max(200, width - axisSize - 4)
  const cellW = Math.max(80, innerW / colCount)
  const cellH = 26
  const height = 40 + cellH * data.length + 4
  const color = scaleLinear<string>({
    domain: [-max, 0, max],
    range: ['rgba(239,68,68,0.95)', 'rgba(60,70,90,0.35)', 'rgba(34,197,94,0.95)'],
  })

  return (
    <svg width={width} height={height}>
      <Group left={axisSize}>
        {REGIME_COLS.map((c, i) => (
          <text
            key={c.key as string}
            x={i * cellW + cellW / 2}
            y={26}
            textAnchor="middle"
            fontSize={10}
            fill="var(--text-2)"
            fontFamily="var(--font-mono)"
          >
            {c.label}
          </text>
        ))}
      </Group>
      <Group top={40}>
        {data.map((r, row) => (
          <text
            key={r.strategy}
            x={axisSize - 6}
            y={row * cellH + cellH / 2 + 3}
            textAnchor="end"
            fontSize={10}
            fill="var(--text-2)"
          >
            {r.strategy.length > 34 ? r.strategy.slice(0, 32) + '…' : r.strategy}
          </text>
        ))}
      </Group>
      <Group left={axisSize} top={40}>
        {data.map((r, row) =>
          REGIME_COLS.map((c, col) => {
            const v = Number(r[c.key] ?? 0)
            return (
              <g key={`${r.strategy}-${c.key as string}`}>
                <rect
                  x={col * cellW + 1}
                  y={row * cellH + 1}
                  width={cellW - 2}
                  height={cellH - 2}
                  fill={color(v)}
                >
                  <title>
                    {r.strategy} — {c.label}: {formatCurrency(v, { signed: true })}
                  </title>
                </rect>
                <text
                  x={col * cellW + cellW / 2}
                  y={row * cellH + cellH / 2 + 3}
                  textAnchor="middle"
                  fontSize={10}
                  fontFamily="var(--font-mono)"
                  fill={Math.abs(v) > max * 0.4 ? '#0b0d12' : 'var(--text-0)'}
                >
                  {formatCurrency(v, { signed: true, precision: 0, compact: true })}
                </text>
              </g>
            )
          }),
        )}
      </Group>
    </svg>
  )
}
