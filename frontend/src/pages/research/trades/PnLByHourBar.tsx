import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { Clock } from 'lucide-react'
import { formatCurrency } from '@/lib/utils'
import type { TradeAnalyticsPayload } from '../useResearchData'

interface PnLByHourBarProps {
  data: TradeAnalyticsPayload | undefined
  loading?: boolean
}

// NYSE regular session in UTC is roughly 13:30-20:00
const SESSION_UTC_START = 13.5
const SESSION_UTC_END = 20

export function PnLByHourBar({ data, loading }: PnLByHourBarProps) {
  const rows = useMemo(() => {
    const map = data?.pnl_by_hour ?? {}
    return Array.from({ length: 24 }, (_, h) => ({
      hour: h,
      label: `${h.toString().padStart(2, '0')}:00`,
      pnl: Number(map[String(h)] ?? 0),
    }))
  }, [data?.pnl_by_hour])

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>P&L by hour (UTC)</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  const hasAny = rows.some((r) => r.pnl !== 0)
  if (!hasAny) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>P&L by hour (UTC)</SectionLabel>
        <EmptyState
          icon={Clock}
          title="No hourly P&L"
          description="Populated from positions closed within the selected period."
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
            shaded band = NYSE regular hours (UTC)
          </span>
        }
      >
        P&L by hour (UTC)
      </SectionLabel>
      <div className="h-[260px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 2, left: 4 }}>
            <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={{ stroke: 'var(--border-subtle)' }}
              tickLine={false}
              interval={2}
            />
            <YAxis
              tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
              axisLine={false}
              tickLine={false}
              width={48}
              tickFormatter={(v: number) => formatCurrency(v, { compact: true, precision: 0 })}
            />
            <ReferenceArea
              x1={rows[Math.floor(SESSION_UTC_START)].label}
              x2={rows[Math.ceil(SESSION_UTC_END)].label}
              fill="color-mix(in oklab, var(--accent-primary) 6%, transparent)"
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
              {rows.map((r, i) => (
                <Cell
                  key={i}
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
