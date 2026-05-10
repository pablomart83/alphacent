import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { BarChart3 } from 'lucide-react'
import { formatNumber } from '@/lib/utils'
import type { ReturnBin } from '../useResearchData'

interface ReturnDistributionPanelProps {
  bins: ReturnBin[] | undefined
  skew: number | undefined
  kurtosis: number | undefined
  loading?: boolean
}

export function ReturnDistributionPanel({
  bins,
  skew,
  kurtosis,
  loading,
}: ReturnDistributionPanelProps) {
  const rows = useMemo(() => (bins ?? []).map((b) => ({
    bin: b.bin,
    count: b.count,
    label: `${(b.bin * 100).toFixed(2)}%`,
    negative: b.bin < 0,
  })), [bins])

  const annualisedVol = useMemo(() => {
    if (!rows.length) return 0
    const totalCount = rows.reduce((a, r) => a + r.count, 0) || 1
    const mean = rows.reduce((a, r) => a + (r.bin * r.count), 0) / totalCount
    const variance = rows.reduce((a, r) => a + r.count * (r.bin - mean) ** 2, 0) / totalCount
    return Math.sqrt(variance) * Math.sqrt(252) * 100
  }, [rows])

  if (loading && !bins) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Return distribution</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Return distribution</SectionLabel>
        <EmptyState
          icon={BarChart3}
          title="No return distribution"
          description="Needs at least two equity snapshots to compute a distribution."
          className="py-8"
        />
      </section>
    )
  }

  const skewNum = Number(skew ?? 0)
  const kurtNum = Number(kurtosis ?? 0)

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            σ (annualised) = {formatNumber(annualisedVol, 2)}% · skew =
            {' '}
            {formatNumber(skewNum, 2)} · kurtosis = {formatNumber(kurtNum, 2)}
          </span>
        }
      >
        Return distribution
      </SectionLabel>
      <div className="h-[280px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <BarChart data={rows} barCategoryGap={1} margin={{ top: 6, right: 12, bottom: 2, left: -8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="bin"
              type="number"
              tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
              domain={['dataMin', 'dataMax']}
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
              labelFormatter={(v) =>
                typeof v === 'number' ? `Bucket ${(v * 100).toFixed(2)}%` : '—'
              }
              formatter={(v) => (typeof v === 'number' ? [`${v} days`, 'Count'] : ['—', 'Count'])}
            />
            <ReferenceLine x={0} stroke="var(--text-3)" strokeDasharray="2 3" />
            <Bar dataKey="count" radius={[2, 2, 0, 0]}>
              {rows.map((r, i) => (
                <Cell key={i} fill={r.negative ? 'var(--pnl-down)' : 'var(--pnl-up)'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
