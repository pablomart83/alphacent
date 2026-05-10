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
import { Timer } from 'lucide-react'
import { useTradeJournal } from '../useResearchData'
import type { TradeAnalyticsPayload } from '../useResearchData'

interface HoldingPeriodHistogramProps {
  data: TradeAnalyticsPayload | undefined
  loading?: boolean
}

const BUCKETS: Array<{ label: string; range: [number, number] }> = [
  { label: '<1h', range: [0, 1] },
  { label: '1–4h', range: [1, 4] },
  { label: '4–12h', range: [4, 12] },
  { label: '12h–1d', range: [12, 24] },
  { label: '1–3d', range: [24, 72] },
  { label: '3–7d', range: [72, 168] },
  { label: '1–2w', range: [168, 336] },
  { label: '2w+', range: [336, Infinity] },
]

/**
 * Per-trade holding-period histogram, computed from trade_journal rows so
 * each bar is a real count, not a Gaussian synthesis of the mean.
 *
 * A parallel summary tile in `data.avg_holding_time_hours` from the trade
 * analytics endpoint is rendered as a reference line so both numbers are
 * visible on the same canvas.
 */
export function HoldingPeriodHistogram({ data, loading }: HoldingPeriodHistogramProps) {
  const journal = useTradeJournal({ limit: 500 })

  const rows = useMemo(() => {
    const trades = journal.data?.trades ?? []
    if (!trades.length) return []
    const counts = BUCKETS.map(() => 0)
    for (const t of trades) {
      const h = t.hold_time_hours
      if (h == null || !Number.isFinite(h) || h < 0) continue
      const idx = BUCKETS.findIndex(
        (b) => h >= b.range[0] && h < (b.range[1] === Infinity ? 1e12 : b.range[1]),
      )
      if (idx >= 0) counts[idx] += 1
    }
    return BUCKETS.map((b, i) => ({ label: b.label, count: counts[i] }))
  }, [journal.data?.trades])

  const mean = data?.avg_holding_time_hours ?? 0
  const meanBucket = BUCKETS.findIndex(
    (b) =>
      mean > 0 && mean >= b.range[0] && mean < (b.range[1] === Infinity ? 1e12 : b.range[1]),
  )

  const isLoading = loading || journal.isLoading

  if (isLoading && !journal.data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Holding period</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.some((r) => r.count > 0)) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Holding period</SectionLabel>
        <EmptyState
          icon={Timer}
          title="No trade journal entries"
          description="Shows once trade_journal rows exist for the selected period."
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
            μ = {mean.toFixed(1)}h · n = {rows.reduce((a, r) => a + r.count, 0)}
          </span>
        }
      >
        Holding period
      </SectionLabel>
      <div className="h-[280px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 2, left: -8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
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
              formatter={(v) => (typeof v === 'number' ? [`${v} trades`, 'Count'] : ['—', 'Count'])}
            />
            {meanBucket >= 0 && (
              <ReferenceLine
                x={BUCKETS[meanBucket].label}
                stroke="var(--accent-primary)"
                strokeDasharray="3 3"
              />
            )}
            <Bar dataKey="count" radius={[2, 2, 0, 0]}>
              {rows.map((_, i) => (
                <Cell
                  key={i}
                  fill={i === meanBucket ? 'var(--accent-primary)' : 'var(--text-3)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
