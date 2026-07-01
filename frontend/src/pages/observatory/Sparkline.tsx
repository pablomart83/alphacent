import { useMemo } from 'react'

interface SparklineProps {
  data: number[]
  width?: number
  height?: number
  className?: string
}

/**
 * Minimal equity sparkline — a trend-at-a-glance replacement for the full
 * equity chart (which belongs on Command, not this observation surface).
 * Coloured up/down by net change; pure SVG, no chart lib.
 */
export function Sparkline({ data, width = 132, height = 34, className }: SparklineProps) {
  const { path, up, flat } = useMemo(() => {
    const pts = data.filter((v) => Number.isFinite(v))
    if (pts.length < 2) return { path: '', up: true, flat: true }
    const min = Math.min(...pts)
    const max = Math.max(...pts)
    const range = max - min || 1
    const stepX = width / (pts.length - 1)
    const d = pts
      .map((v, i) => {
        const x = i * stepX
        const y = height - ((v - min) / range) * height
        return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`
      })
      .join(' ')
    return { path: d, up: pts[pts.length - 1] >= pts[0], flat: false }
  }, [data, width, height])

  const color = flat ? 'var(--pnl-flat)' : up ? 'var(--pnl-up)' : 'var(--pnl-down)'

  if (!path) {
    return <div style={{ width, height }} className={className} aria-hidden />
  }

  return (
    <svg width={width} height={height} className={className} role="img" aria-label="Equity trend">
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  )
}
