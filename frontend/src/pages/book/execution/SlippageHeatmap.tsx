import { useMemo } from 'react'
import { Group } from '@visx/group'
import { HeatmapRect } from '@visx/heatmap'
import { scaleLinear } from '@visx/scale'
import { EmptyState } from '@/components/primitives'
import { Clock } from 'lucide-react'
import type { SlippageHeatmapCell } from './computeMetrics'

const DOW_LABELS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

interface BinDatum {
  bin: number
  count: number
  hasData: boolean
}

interface ColumnDatum {
  bin: number
  bins: BinDatum[]
}

/**
 * Filled-order slippage (bps) averaged over day-of-week × hour-of-day (UTC).
 * Cells with no data render as transparent (structural) rather than green-0.
 */
export function SlippageHeatmap({
  cells,
  width,
  height = 180,
}: {
  cells: SlippageHeatmapCell[]
  width: number
  height?: number
}) {
  const hasAny = cells.some((c) => c.avgBps != null)

  const { columns, colorScale, opacityScale } = useMemo(() => {
    // columns[hour] = { bin: hour, bins: [per dow] }
    const cols: ColumnDatum[] = Array.from({ length: 24 }, (_, hour) => ({
      bin: hour,
      bins: Array.from({ length: 7 }, (_, dow) => {
        const match = cells.find((c) => c.hour === hour && c.dow === dow)
        const v = match?.avgBps ?? 0
        return {
          bin: dow,
          count: v,
          hasData: !!(match && match.count > 0),
        }
      }),
    }))

    const values = cells
      .filter((c) => c.avgBps != null && Number.isFinite(c.avgBps))
      .map((c) => c.avgBps as number)
    const min = values.length ? Math.min(...values) : -10
    const max = values.length ? Math.max(...values) : 10
    const bound = Math.max(Math.abs(min), Math.abs(max), 1)

    // Diverging scale: negative (favourable) = green, positive (adverse) = red.
    const color = scaleLinear<string>({
      domain: [-bound, 0, bound],
      range: ['rgba(34,197,94,0.9)', 'rgba(120,130,150,0.4)', 'rgba(239,68,68,0.9)'],
    })
    const opacity = scaleLinear<number>({
      domain: [0, bound],
      range: [0.3, 1],
    })

    return { columns: cols, colorScale: color, opacityScale: opacity }
  }, [cells])

  if (!hasAny) {
    return (
      <EmptyState
        icon={Clock}
        title="No slippage by hour yet"
        description="Populates as fills accumulate. 3+ fills per cell needed for a meaningful average."
        className="py-6"
      />
    )
  }

  // Leave room for axes.
  const axisLeftWidth = 32
  const axisBottomHeight = 20
  const innerW = Math.max(120, width - axisLeftWidth - 8)
  const innerH = Math.max(90, height - axisBottomHeight - 8)

  const binWidth = innerW / 24
  const binHeight = innerH / 7

  return (
    <svg width={width} height={height}>
      {/* Y labels */}
      <Group left={0} top={0}>
        {DOW_LABELS.map((label, i) => (
          <text
            key={label}
            x={axisLeftWidth - 4}
            y={i * binHeight + binHeight / 2 + 3}
            textAnchor="end"
            fontSize={9}
            fill="var(--text-3)"
            fontFamily="var(--font-mono)"
          >
            {label}
          </text>
        ))}
      </Group>
      {/* X labels: every 3 hours */}
      <Group left={axisLeftWidth} top={innerH + 2}>
        {Array.from({ length: 24 }, (_, i) => i)
          .filter((i) => i % 3 === 0)
          .map((i) => (
            <text
              key={i}
              x={i * binWidth + binWidth / 2}
              y={12}
              textAnchor="middle"
              fontSize={9}
              fill="var(--text-3)"
              fontFamily="var(--font-mono)"
            >
              {String(i).padStart(2, '0')}
            </text>
          ))}
      </Group>
      {/* Cells */}
      <HeatmapRect<ColumnDatum, BinDatum>
        data={columns}
        xScale={(columnIndex) => axisLeftWidth + columnIndex * binWidth}
        yScale={(rowIndex) => rowIndex * binHeight}
        colorScale={colorScale}
        opacityScale={opacityScale}
        binWidth={binWidth}
        binHeight={binHeight}
        gap={1}
        bins={(d) => d.bins}
        count={(b) => b.count}
      >
        {(heatmap) =>
          heatmap.map((cols) =>
            cols.map((cell) => {
              const bin = cell.bin
              if (!bin.hasData) {
                return (
                  <rect
                    key={`empty-${cell.row}-${cell.column}`}
                    x={cell.x}
                    y={cell.y}
                    width={cell.width}
                    height={cell.height}
                    fill="var(--bg-2)"
                    opacity={0.5}
                  />
                )
              }
              return (
                <rect
                  key={`cell-${cell.row}-${cell.column}`}
                  x={cell.x}
                  y={cell.y}
                  width={cell.width}
                  height={cell.height}
                  fill={cell.color}
                  fillOpacity={cell.opacity}
                >
                  <title>
                    {`${DOW_LABELS[cell.row]} ${String(cell.column).padStart(2, '0')}:00 UTC — ${
                      Number.isFinite(bin.count) ? `${bin.count >= 0 ? '+' : ''}${bin.count.toFixed(1)} bps` : 'no data'
                    }`}
                  </title>
                </rect>
              )
            }),
          )
        }
      </HeatmapRect>
    </svg>
  )
}
