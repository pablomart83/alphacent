import { useMemo } from 'react'
import { Cell, Legend, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { PieChart as PieIcon } from 'lucide-react'
import type { TradeAnalyticsPayload } from '../useResearchData'

interface WinLossDistributionPieProps {
  data: TradeAnalyticsPayload | undefined
  loading?: boolean
}

const COLORS: Record<string, string> = {
  large_wins: 'var(--pnl-up)',
  medium_wins: 'color-mix(in oklab, var(--pnl-up) 70%, var(--bg-1))',
  small_wins: 'color-mix(in oklab, var(--pnl-up) 45%, var(--bg-1))',
  small_losses: 'color-mix(in oklab, var(--pnl-down) 45%, var(--bg-1))',
  medium_losses: 'color-mix(in oklab, var(--pnl-down) 70%, var(--bg-1))',
  large_losses: 'var(--pnl-down)',
}

const LABELS: Record<string, string> = {
  large_wins: 'Large wins',
  medium_wins: 'Medium wins',
  small_wins: 'Small wins',
  small_losses: 'Small losses',
  medium_losses: 'Medium losses',
  large_losses: 'Large losses',
}

export function WinLossDistributionPie({ data, loading }: WinLossDistributionPieProps) {
  const rows = useMemo(() => {
    if (!data?.win_loss_distribution) return []
    return Object.entries(data.win_loss_distribution)
      .filter(([, v]) => v > 0)
      .map(([k, v]) => ({
        key: k,
        name: LABELS[k] ?? k,
        value: v,
      }))
  }, [data?.win_loss_distribution])

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Win / loss distribution</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Win / loss distribution</SectionLabel>
        <EmptyState
          icon={PieIcon}
          title="No closed trades"
          description="Once trades close in this period, the breakdown appears here."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Win / loss distribution</SectionLabel>
      <div className="h-[280px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <PieChart>
            <Pie
              data={rows}
              dataKey="value"
              nameKey="name"
              outerRadius="75%"
              innerRadius="45%"
              stroke="var(--bg-1)"
              strokeWidth={1.5}
            >
              {rows.map((r) => (
                <Cell key={r.key} fill={COLORS[r.key] ?? 'var(--text-3)'} />
              ))}
            </Pie>
            <Tooltip
              contentStyle={{
                background: 'var(--bg-2)',
                border: '1px solid var(--border-subtle)',
                fontSize: 11,
                borderRadius: 3,
              }}
              formatter={(v, name) =>
                typeof v === 'number' ? [`${v} trades`, String(name)] : ['—', String(name)]
              }
            />
            <Legend
              wrapperStyle={{ fontSize: 10, color: 'var(--text-2)' }}
              iconSize={8}
              verticalAlign="bottom"
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
