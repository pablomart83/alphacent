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
import { CalendarDays } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import type { TradeAnalyticsPayload } from '../useResearchData'

interface PnLByDayOfWeekBarProps {
  data: TradeAnalyticsPayload | undefined
  loading?: boolean
}

const DAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
]

export function PnLByDayOfWeekBar({ data, loading }: PnLByDayOfWeekBarProps) {
  const rows = useMemo(() => {
    const map = data?.pnl_by_day ?? {}
    return DAYS.map((d) => ({
      day: d,
      label: d.slice(0, 3),
      pnl: Number(map[d] ?? 0),
    }))
  }, [data?.pnl_by_day])

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>P&L by day of week</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.some((r) => r.pnl !== 0)) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>P&L by day of week</SectionLabel>
        <EmptyState
          icon={CalendarDays}
          title="No day-of-week data"
          description="Populated from positions closed within the selected period."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>P&L by day of week</SectionLabel>
      <div className="h-[220px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 2, left: 4 }}>
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
              width={52}
              tickFormatter={(v: number) => formatCurrency(v, { compact: true, precision: 0 })}
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
                  ? [formatCurrency(v, { signed: true }), 'P&L']
                  : ['—', 'P&L']
              }
            />
            <Bar dataKey="pnl" radius={[2, 2, 0, 0]}>
              {rows.map((r) => (
                <Cell
                  key={r.day}
                  fill={r.pnl >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  )
}
