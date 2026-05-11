import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { Target } from 'lucide-react'
import type { StrategyAttribution } from '../useResearchData'

interface StrategyContributionBarProps {
  rows: StrategyAttribution[] | undefined
  loading?: boolean
}

export function StrategyContributionBar({ rows, loading }: StrategyContributionBarProps) {
  const top = useMemo(() => {
    if (!rows) return []
    return [...rows]
      .sort((a, b) => Math.abs(b.total_return) - Math.abs(a.total_return))
      .slice(0, 15)
      .sort((a, b) => b.total_return - a.total_return)
  }, [rows])

  if (loading && !rows) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Top 15 contributors</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!top.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Top 15 contributors</SectionLabel>
        <EmptyState
          icon={Target}
          title="No strategy-level P&L yet"
          description="Contributors appear once strategies have closed-out positions."
          className="py-8"
        />
      </section>
    )
  }

  const height = Math.max(260, top.length * 22 + 40)

  return (
    <section className="space-y-1.5">
      <SectionLabel>Top 15 contributors</SectionLabel>
      <div
        className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1"
        style={{ height: `${height}px` }}
      >
        <ResponsiveContainer>
          <BarChart data={top} layout="vertical" margin={{ top: 4, right: 48, bottom: 2, left: 8 }}>
            <XAxis
              type="number"
              tickFormatter={(v: number) => `${v.toFixed(0)}%`}
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
            />
            <YAxis
              dataKey="strategy_name"
              type="category"
              width={150}
              tick={{ fill: 'var(--text-2)', fontSize: 10 }}
              interval={0}
              axisLine={false}
              tickLine={false}
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
                typeof v === 'number' ? [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, 'Return'] : ['—', 'Return']
              }
            />
            <Bar dataKey="total_return" radius={[0, 2, 2, 0]}>
              {top.map((r) => (
                <Cell
                  key={r.strategy_id}
                  fill={r.total_return >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'}
                />
              ))}
              <LabelList
                dataKey="total_return"
                position="right"
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
