import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  ReferenceLine,
  Cell,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { TrendingDown } from 'lucide-react'
import { formatPercentage } from '@/lib/utils'
import type { EquityCurvePointApi } from '../useResearchData'

interface ReturnsDistributionHistogramProps {
  equityCurve: EquityCurvePointApi[] | undefined
  loading: boolean
}

interface Bucket {
  label: string
  mid: number
  count: number
  negative: boolean
}

/** Derive daily-return % histogram from the equity curve directly. */
export function ReturnsDistributionHistogram({
  equityCurve,
  loading,
}: ReturnsDistributionHistogramProps) {
  const { buckets, mean, std, n } = useMemo(() => {
    if (!equityCurve || equityCurve.length < 2) {
      return { buckets: [] as Bucket[], mean: 0, std: 0, n: 0 }
    }
    const returns: number[] = []
    for (let i = 1; i < equityCurve.length; i++) {
      const prev = equityCurve[i - 1].equity
      const now = equityCurve[i].equity
      if (prev > 0) returns.push(((now - prev) / prev) * 100)
    }
    if (!returns.length) return { buckets: [] as Bucket[], mean: 0, std: 0, n: 0 }
    const mean = returns.reduce((a, b) => a + b, 0) / returns.length
    const variance =
      returns.reduce((sum, r) => sum + (r - mean) ** 2, 0) /
      Math.max(returns.length - 1, 1)
    const std = Math.sqrt(variance)
    // Build symmetric buckets centred on 0, width = max(|max|,|min|)/10
    const max = Math.max(...returns.map((r) => Math.abs(r)), 1e-6)
    const step = Math.max(max / 10, 0.1)
    const bucketMap = new Map<number, number>()
    for (const r of returns) {
      const idx = Math.round(r / step)
      bucketMap.set(idx, (bucketMap.get(idx) ?? 0) + 1)
    }
    const buckets: Bucket[] = Array.from(bucketMap.entries())
      .sort((a, b) => a[0] - b[0])
      .map(([idx, count]) => ({
        mid: idx * step,
        label: `${(idx * step).toFixed(2)}%`,
        count,
        negative: idx * step < 0,
      }))
    return { buckets, mean, std, n: returns.length }
  }, [equityCurve])

  if (loading && !equityCurve) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Returns distribution</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!buckets.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Returns distribution</SectionLabel>
        <EmptyState
          icon={TrendingDown}
          title="Not enough equity history"
          description="At least two equity snapshots are needed to compute a return distribution."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            n={n} · μ={formatPercentage(mean, { precision: 2 })} · σ=
            {formatPercentage(std, { precision: 2, signed: false })}
          </span>
        }
      >
        Returns distribution
      </SectionLabel>
      <div className="h-[260px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          {/* Use category XAxis (dataKey="label") so Recharts auto-sizes bar widths.
              A numeric XAxis with Bar produces zero-width bars unless barSize is set. */}
          <BarChart data={buckets} barCategoryGap="2%" margin={{ top: 6, right: 12, bottom: 2, left: -8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              width={28}
              allowDecimals={false}
            />
            <Tooltip
              cursor={{ fill: 'var(--bg-hover)' }}
              contentStyle={{
                background: 'var(--bg-2)',
                border: '1px solid var(--border-subtle)',
                fontSize: 11,
                borderRadius: 3,
              }}
              labelFormatter={(v) => `Bucket ${v}`}
              formatter={(v) => (typeof v === 'number' ? [`${v} days`, 'Count'] : ['—', 'Count'])}
            />
            {/* Reference lines use x= with the label string for category axis */}
            <ReferenceLine
              x={buckets.reduce((closest, b) => Math.abs(b.mid) < Math.abs(closest.mid) ? b : closest, buckets[0])?.label}
              stroke="var(--text-3)"
              strokeDasharray="2 3"
              label={{ value: '0', fill: 'var(--text-3)', fontSize: 9, position: 'top' }}
            />
            <ReferenceLine
              x={buckets.reduce((closest, b) => Math.abs(b.mid - mean) < Math.abs(closest.mid - mean) ? b : closest, buckets[0])?.label}
              stroke="var(--accent-primary)"
              strokeDasharray="4 3"
              label={{ value: 'μ', fill: 'var(--accent-primary)', fontSize: 9, position: 'top' }}
            />
            <Bar dataKey="count" radius={[2, 2, 0, 0]}>
              {buckets.map((b, i) => (
                <Cell key={i} fill={b.negative ? 'var(--pnl-down)' : 'var(--pnl-up)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
