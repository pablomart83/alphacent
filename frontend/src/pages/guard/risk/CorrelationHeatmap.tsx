import { memo, useMemo, useState } from 'react'
import { Group } from '@visx/group'
import { scaleLinear } from '@visx/scale'
import { ParentSize } from '@visx/responsive'
import {
  EmptyState,
  Input,
  Label,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { Network } from 'lucide-react'
import type { CorrelatedPair } from '../useGuardData'

// Module-level constant — created once, never recreated on re-render.
const COLOR_SCALE = scaleLinear<string>({
  domain: [-1, 0, 1],
  range: ['rgba(34,197,94,0.9)', 'rgba(120,130,150,0.2)', 'rgba(239,68,68,0.9)'],
})

interface CorrelationHeatmapProps {
  pairs: CorrelatedPair[] | null | undefined
  loading?: boolean
}

/**
 * CorrelationHeatmap — symmetric matrix of |ρ| over the distinct symbols in
 * `correlated_pairs` from /risk/advanced. Threshold slider filters low-|ρ|
 * cells so the CIO can surface just the concentration risk.
 *
 * Diagonal is always 1.0 (self-correlation). The backend only returns top N
 * pairs so unseen combos render as "—" rather than zero.
 */
export function CorrelationHeatmap({ pairs, loading }: CorrelationHeatmapProps) {
  const [threshold, setThreshold] = useState(0.3)

  const { symbols, matrix } = useMemo(() => {
    if (!pairs?.length) return { symbols: [] as string[], matrix: new Map<string, number>() }
    const sym = new Set<string>()
    const m = new Map<string, number>()
    for (const p of pairs) {
      sym.add(p.symbol_a)
      sym.add(p.symbol_b)
      const key = [p.symbol_a, p.symbol_b].sort().join('::')
      m.set(key, p.correlation)
    }
    return {
      symbols: Array.from(sym).sort(),
      matrix: m,
    }
  }, [pairs])

  const above = useMemo(
    () => (pairs ?? []).filter((p) => Math.abs(p.correlation) >= threshold).length,
    [pairs, threshold],
  )

  if (loading && !pairs) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Position correlations</SectionLabel>
        <div className="h-[260px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (!symbols.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Position correlations</SectionLabel>
        <EmptyState
          icon={Network}
          title="No correlated pairs"
          description="Correlations computed from 60-90 day close-to-close returns once ≥ 2 open positions exist."
          className="py-6"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <SectionLabel className="mb-0">Position correlations</SectionLabel>
        <div className="flex items-center gap-2">
          <Label className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
            |ρ| ≥
          </Label>
          <Input
            type="number"
            value={threshold}
            onChange={(e) => setThreshold(Number(e.target.value))}
            min={0}
            max={1}
            step={0.05}
            className="h-6 w-[60px] mono text-[10px] text-right"
          />
          <span className="text-[10px] text-[var(--text-3)]">
            {above} of {pairs?.length ?? 0} above threshold
          </span>
        </div>
      </div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <ParentSize debounceTime={50}>
          {({ width }) => (
            <HeatmapSvg
              symbols={symbols}
              matrix={matrix}
              threshold={threshold}
              width={Math.max(320, width)}
            />
          )}
        </ParentSize>
        <div className="flex items-center gap-3 text-[9px] text-[var(--text-3)] uppercase tracking-wider mt-2 px-1">
          <ScaleLegendChip label="Negative" color="rgba(34,197,94,0.9)" />
          <ScaleLegendChip label="None" color="rgba(120,130,150,0.3)" />
          <ScaleLegendChip label="Positive" color="rgba(239,68,68,0.9)" />
          <span className="ml-auto">
            Below threshold rendered faint · hover for value
          </span>
        </div>
      </div>
    </section>
  )
}

// Memoised so it only repaints when symbols, matrix, threshold, or width
// actually change — not on every parent re-render from polling.
const HeatmapSvg = memo(function HeatmapSvg({
  symbols,
  matrix,
  threshold,
  width,
}: {
  symbols: string[]
  matrix: Map<string, number>
  threshold: number
  width: number
}) {
  const axisSize = 60
  const innerW = Math.max(120, width - axisSize)
  const cellSize = Math.max(14, Math.min(40, innerW / symbols.length))
  const height = axisSize + cellSize * symbols.length

  return (
    <svg width={width} height={height}>
      {/* Column labels — top */}
      <Group left={axisSize}>
        {symbols.map((s, i) => (
          <text
            key={`col-${s}`}
            x={i * cellSize + cellSize / 2}
            y={axisSize - 6}
            textAnchor="end"
            transform={`rotate(-55, ${i * cellSize + cellSize / 2}, ${axisSize - 6})`}
            fontSize={9}
            fill="var(--text-2)"
            fontFamily="var(--font-mono)"
          >
            {s}
          </text>
        ))}
      </Group>
      {/* Row labels — left */}
      <Group top={axisSize}>
        {symbols.map((s, i) => (
          <text
            key={`row-${s}`}
            x={axisSize - 4}
            y={i * cellSize + cellSize / 2 + 3}
            textAnchor="end"
            fontSize={9}
            fill="var(--text-2)"
            fontFamily="var(--font-mono)"
          >
            {s}
          </text>
        ))}
      </Group>
      {/* Cells */}
      <Group left={axisSize} top={axisSize}>
        {symbols.map((rowSym, r) =>
          symbols.map((colSym, c) => {
            const isDiag = r === c
            let value: number | null = null
            if (isDiag) {
              value = 1
            } else {
              const key = [rowSym, colSym].sort().join('::')
              value = matrix.has(key) ? (matrix.get(key) as number) : null
            }
            const hasValue = value != null
            const belowThreshold = hasValue && Math.abs(value as number) < threshold
            const fill = hasValue ? COLOR_SCALE(value as number) : 'var(--bg-2)'
            const opacity = !hasValue ? 0.3 : belowThreshold ? 0.25 : 1
            return (
              <rect
                key={`${rowSym}-${colSym}`}
                x={c * cellSize + 1}
                y={r * cellSize + 1}
                width={cellSize - 2}
                height={cellSize - 2}
                fill={fill}
                opacity={opacity}
              >
                <title>
                  {hasValue
                    ? `${rowSym} × ${colSym} — ρ = ${(value as number).toFixed(2)}`
                    : `${rowSym} × ${colSym} — no data`}
                </title>
              </rect>
            )
          }),
        )}
      </Group>
    </svg>
  )
})

function ScaleLegendChip({ label, color }: { label: string; color: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="h-1.5 w-3 rounded-[1px]" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}
