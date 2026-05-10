import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { BarChart3 } from 'lucide-react'
import type { AnnualReturn } from '../useResearchData'

interface AnnualReturnsBarProps {
  data: AnnualReturn[]
  loading?: boolean
}

export function AnnualReturnsBar({ data, loading }: AnnualReturnsBarProps) {
  if (loading && !data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Annual returns</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }
  if (!data.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Annual returns</SectionLabel>
        <EmptyState
          icon={BarChart3}
          title="No calendar-year returns"
          description="Once at least one full calendar month of snapshots exists, this view populates."
          className="py-8"
        />
      </section>
    )
  }
  return (
    <section className="space-y-1.5">
      <SectionLabel>Annual returns</SectionLabel>
      <div className="h-[220px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 14, right: 12, bottom: 2, left: -8 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="year"
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
            />
            <YAxis
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              width={36}
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
            />
            <Tooltip
              cursor={{ fill: 'var(--bg-hover)' }}
              contentStyle={{
                background: 'var(--bg-2)',
                border: '1px solid var(--border-subtle)',
                fontSize: 11,
                borderRadius: 3,
              }}
              formatter={(v) =>
                typeof v === 'number'
                  ? [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, 'Return']
                  : ['—', 'Return']
              }
            />
            <Bar dataKey="return_pct" radius={[2, 2, 0, 0]}>
              {data.map((d) => (
                <Cell
                  key={d.year}
                  fill={d.return_pct >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'}
                />
              ))}
              <LabelList
                dataKey="return_pct"
                position="top"
                fill="var(--text-2)"
                fontSize={10}
                formatter={(v) =>
                  typeof v === 'number' ? `${v > 0 ? '+' : ''}${v.toFixed(1)}%` : '—'
                }
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
