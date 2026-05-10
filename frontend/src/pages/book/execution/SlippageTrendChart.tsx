import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { SlippageTrendPoint } from './computeMetrics'
import { EmptyState } from '@/components/primitives'
import { TrendingUp } from 'lucide-react'

/** Daily P50 / P75 / P95 slippage over the selected period. */
export function SlippageTrendChart({
  data,
  height = 180,
}: {
  data: SlippageTrendPoint[]
  height?: number
}) {
  if (data.length === 0) {
    return (
      <EmptyState
        icon={TrendingUp}
        title="No slippage data in range"
        description="Filled entry orders with expected vs filled prices populate this trend."
        className="py-6"
      />
    )
  }

  return (
    <div style={{ width: '100%', height }}>
      <ResponsiveContainer>
        <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid strokeDasharray="2 3" stroke="var(--border-subtle)" />
          <XAxis
            dataKey="date"
            tick={{ fontSize: 10, fill: 'var(--text-3)' }}
            stroke="var(--border-subtle)"
            tickFormatter={(v: string) => v.slice(5)}
          />
          <YAxis
            tick={{ fontSize: 10, fill: 'var(--text-3)' }}
            stroke="var(--border-subtle)"
            tickFormatter={(v) => `${v.toFixed(0)}`}
            width={36}
            label={{ value: 'bps', angle: -90, position: 'insideLeft', style: { fill: 'var(--text-3)', fontSize: 10 } }}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--bg-2)',
              border: '1px solid var(--border-default)',
              borderRadius: 3,
              fontSize: 11,
              color: 'var(--text-0)',
            }}
            formatter={(v) => (typeof v === 'number' ? `${v.toFixed(1)} bps` : '—')}
          />
          <Line type="monotone" dataKey="p50" stroke="var(--accent-primary)" strokeWidth={2} dot={false} name="P50" />
          <Line type="monotone" dataKey="p75" stroke="var(--status-warning)" strokeWidth={1.5} dot={false} name="P75" strokeDasharray="4 3" />
          <Line type="monotone" dataKey="p95" stroke="var(--pnl-down)" strokeWidth={1} dot={false} name="P95" strokeDasharray="2 3" />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
