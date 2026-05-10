import { useMemo } from 'react'
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { EmptyState, Skeleton } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { LineChart as LineIcon } from 'lucide-react'
import { formatPercentage, formatTimestamp } from '@/lib/utils'
import type { RiskHistoryPayload } from '../useGuardData'

interface RiskScoreTrendChartProps {
  data: RiskHistoryPayload | null | undefined
  loading?: boolean
}

/**
 * RiskScoreTrendChart — plots drawdown + leverage × 10 over the window.
 * Drawdown is the single most-watched risk time series; leverage is
 * overlaid on a secondary axis-less line to see if one is driving the other.
 */
export function RiskScoreTrendChart({ data, loading }: RiskScoreTrendChartProps) {
  const series = useMemo(() => {
    const points = data?.history ?? []
    return points.map((p) => ({
      t: p.timestamp,
      drawdown: Number.isFinite(p.drawdown) ? p.drawdown : null,
      leverage: Number.isFinite(p.leverage) ? p.leverage : null,
    }))
  }, [data])

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Risk trend · 30d</SectionLabel>
        <Skeleton className="h-[200px] w-full" />
      </section>
    )
  }

  if (!series.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Risk trend</SectionLabel>
        <EmptyState
          icon={LineIcon}
          title="No risk history yet"
          description="Populates as daily equity snapshots accumulate."
          className="py-6"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Risk trend · {data?.period ?? '30d'}</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
        <div style={{ width: '100%', height: 200 }}>          <ResponsiveContainer>
            <LineChart data={series} margin={{ top: 6, right: 12, bottom: 0, left: -8 }}>
              <CartesianGrid
                stroke="var(--border-subtle)"
                strokeDasharray="3 3"
                vertical={false}
              />
              <XAxis
                dataKey="t"
                tickFormatter={(t) => formatTimestamp(t, 'short') || ''}
                tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border-subtle)' }}
              />
              <YAxis
                yAxisId="dd"
                tickFormatter={(v) => `${typeof v === 'number' ? v.toFixed(0) : '0'}%`}
                tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                width={36}
              />
              <YAxis
                yAxisId="lev"
                orientation="right"
                tickFormatter={(v) => `${typeof v === 'number' ? v.toFixed(1) : '0'}×`}
                tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                tickLine={false}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                width={36}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-2)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 3,
                  fontSize: 11,
                }}
                formatter={(value, name) => {
                  if (typeof value !== 'number') return ['—', name as string]
                  if (name === 'drawdown') return [formatPercentage(value, { precision: 2 }), 'Drawdown']
                  return [`${value.toFixed(2)}×`, 'Leverage']
                }}
                labelFormatter={(t) => formatTimestamp(String(t), 'long') || ''}
              />
              <Line
                yAxisId="dd"
                type="monotone"
                dataKey="drawdown"
                stroke="var(--pnl-down)"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                name="drawdown"
              />
              <Line
                yAxisId="lev"
                type="monotone"
                dataKey="leverage"
                stroke="var(--accent-primary)"
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
                name="leverage"
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
        <div className="flex items-center gap-3 text-[9px] text-[var(--text-3)] uppercase tracking-wider mt-1">
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3" style={{ backgroundColor: 'var(--pnl-down)' }} />
            Drawdown %
          </span>
          <span className="inline-flex items-center gap-1">
            <span className="h-0.5 w-3" style={{ backgroundColor: 'var(--accent-primary)' }} />
            Leverage ×
          </span>
        </div>
      </div>
    </section>
  )
}
