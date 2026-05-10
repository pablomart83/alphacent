import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { Ruler } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import { useTradeJournal, type TradeAnalyticsPayload } from '../useResearchData'

interface TradeSizeDistributionProps {
  data: TradeAnalyticsPayload | undefined
  loading?: boolean
}

// Dollar-size buckets tailored to AlphaCent sizing policy
const BUCKETS: Array<{ label: string; range: [number, number] }> = [
  { label: '<500', range: [0, 500] },
  { label: '500–1k', range: [500, 1000] },
  { label: '1–2k', range: [1000, 2000] },
  { label: '2–5k', range: [2000, 5000] },
  { label: '5–10k', range: [5000, 10_000] },
  { label: '10–20k', range: [10_000, 20_000] },
  { label: '20k+', range: [20_000, Infinity] },
]

/** Trade-size distribution from trade journal `entry_size` (invested dollars). */
export function TradeSizeDistribution({ data: _unused, loading }: TradeSizeDistributionProps) {
  const journal = useTradeJournal({ limit: 500 })

  const rows = useMemo(() => {
    const trades = journal.data?.trades ?? []
    const counts = BUCKETS.map(() => 0)
    const pnl = BUCKETS.map(() => 0)
    for (const t of trades) {
      const size = Math.abs(t.entry_size ?? 0)
      if (!size) continue
      const idx = BUCKETS.findIndex(
        (b) => size >= b.range[0] && size < (b.range[1] === Infinity ? 1e12 : b.range[1]),
      )
      if (idx >= 0) {
        counts[idx] += 1
        if (typeof t.pnl === 'number') pnl[idx] += t.pnl
      }
    }
    return BUCKETS.map((b, i) => ({
      label: b.label,
      count: counts[i],
      pnl: pnl[i],
    }))
  }, [journal.data?.trades])

  const isLoading = loading || journal.isLoading

  if (isLoading && !journal.data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Trade-size distribution ($)</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.some((r) => r.count > 0)) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Trade-size distribution ($)</SectionLabel>
        <EmptyState
          icon={Ruler}
          title="No trade-size data"
          description="Shows once trade_journal rows exist with non-zero entry_size."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Trade-size distribution ($)</SectionLabel>
      <div className="h-[220px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
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
              formatter={(v, name, item) => {
                if (typeof v !== 'number') return ['—', String(name)]
                const pnl = Number(item?.payload?.pnl ?? 0)
                return [
                  `${v} trades · Σ P&L ${formatCurrency(pnl, { signed: true, precision: 0 })}`,
                  'Bucket',
                ]
              }}
            />
            <Bar dataKey="count" radius={[2, 2, 0, 0]}>
              {rows.map((r) => (
                <Cell
                  key={r.label}
                  fill={r.pnl > 0 ? 'var(--pnl-up)' : r.pnl < 0 ? 'var(--pnl-down)' : 'var(--text-3)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
