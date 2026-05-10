import { useMemo } from 'react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ComposedChart,
  Legend,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { SectionLabel } from '@/components/layout'
import { EmptyState, Skeleton } from '@/components/primitives'
import { Gauge } from 'lucide-react'
import { formatNumber } from '@/lib/utils'
import type { ConvictionDistributionPayload } from '../useResearchData'

interface ConvictionDistributionChartProps {
  data: ConvictionDistributionPayload | undefined
  loading?: boolean
}

/** Thresholds are documented in the steering file — DEMO 65/70, LIVE 74. */
const THRESHOLD_DEMO = 65
const THRESHOLD_LIVE = 74

export function ConvictionDistributionChart({
  data,
  loading,
}: ConvictionDistributionChartProps) {
  const rows = useMemo(() => {
    if (!data?.score_ranges) return []
    return data.score_ranges.map((r) => {
      // `range` is usually like "60-65" — derive midpoint for the x-axis.
      const range = String(r.range ?? '')
      const match = range.match(/(\d+)[–-](\d+)/)
      const mid = match
        ? (Number(match[1]) + Number(match[2])) / 2
        : typeof r.avg_score === 'number'
          ? r.avg_score
          : 0
      return {
        range,
        mid,
        count: Number(r.count ?? 0),
        win_rate: num(r.win_rate),
        avg_pnl: num(r.avg_pnl),
      }
    })
  }, [data?.score_ranges])

  if (loading && !data) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Conviction score distribution</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!rows.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Conviction score distribution</SectionLabel>
        <EmptyState
          icon={Gauge}
          title="No conviction data"
          description="Distribution populates once the proposer has emitted scored strategies."
          className="py-8"
        />
      </section>
    )
  }

  const hasWinRate = rows.some((r) => r.win_rate != null)
  const hasPnl = rows.some((r) => r.avg_pnl != null)

  return (
    <section className="space-y-1.5">
      <SectionLabel
        actions={
          <span className="text-[10px] normal-case tracking-normal text-[var(--text-3)]">
            μ={formatNumber(data?.avg_score ?? 0, 1)} · med={formatNumber(data?.median_score ?? 0, 1)} · range [
            {formatNumber(data?.min_score ?? 0, 0)}, {formatNumber(data?.max_score ?? 0, 0)}]
          </span>
        }
      >
        Conviction score distribution
      </SectionLabel>
      <div className="h-[320px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
        <ResponsiveContainer>
          {hasWinRate || hasPnl ? (
            <ComposedChart data={rows} margin={{ top: 4, right: 12, bottom: 2, left: -8 }}>
              <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="range"
                tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                yAxisId="count"
                tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                axisLine={false}
                tickLine={false}
                width={30}
              />
              {hasWinRate && (
                <YAxis
                  yAxisId="pct"
                  orientation="right"
                  tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  axisLine={false}
                  tickLine={false}
                  width={38}
                  domain={[0, 100]}
                  tickFormatter={(v: number) => `${v}%`}
                />
              )}
              <Tooltip
                cursor={{ fill: 'var(--bg-hover)' }}
                contentStyle={{
                  background: 'var(--bg-2)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: 11,
                  borderRadius: 3,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 10, color: 'var(--text-2)' }} iconSize={10} />
              <ReferenceLine
                yAxisId="count"
                x={bucketForThreshold(rows, THRESHOLD_DEMO)}
                stroke="var(--accent-primary)"
                strokeDasharray="4 3"
                label={{ value: 'DEMO 65', fill: 'var(--accent-primary)', fontSize: 10, position: 'top' }}
              />
              <ReferenceLine
                yAxisId="count"
                x={bucketForThreshold(rows, THRESHOLD_LIVE)}
                stroke="var(--pnl-up)"
                strokeDasharray="4 3"
                label={{ value: 'LIVE 74', fill: 'var(--pnl-up)', fontSize: 10, position: 'top' }}
              />
              <Bar yAxisId="count" dataKey="count" name="Trades" radius={[2, 2, 0, 0]}>
                {rows.map((r, i) => (
                  <Cell
                    key={i}
                    fill={
                      r.mid >= THRESHOLD_LIVE
                        ? 'var(--pnl-up)'
                        : r.mid >= THRESHOLD_DEMO
                          ? 'var(--accent-primary)'
                          : 'var(--text-3)'
                    }
                  />
                ))}
              </Bar>
              {hasWinRate && (
                <Line
                  yAxisId="pct"
                  type="monotone"
                  dataKey="win_rate"
                  name="Win %"
                  stroke="var(--regime-up)"
                  strokeWidth={1.5}
                  dot={{ r: 2 }}
                  connectNulls
                />
              )}
            </ComposedChart>
          ) : (
            <BarChart data={rows} margin={{ top: 4, right: 12, bottom: 2, left: -8 }}>
              <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="range"
                tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
              />
              <YAxis
                tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                axisLine={false}
                tickLine={false}
                width={30}
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
              />
              <Bar dataKey="count" radius={[2, 2, 0, 0]}>
                {rows.map((r, i) => (
                  <Cell
                    key={i}
                    fill={
                      r.mid >= THRESHOLD_LIVE
                        ? 'var(--pnl-up)'
                        : r.mid >= THRESHOLD_DEMO
                          ? 'var(--accent-primary)'
                          : 'var(--text-3)'
                    }
                  />
                ))}
              </Bar>
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </section>
  )
}

function bucketForThreshold(
  rows: Array<{ range: string; mid: number }>,
  t: number,
): string | undefined {
  for (const r of rows) {
    if (r.mid >= t) return r.range
  }
  return undefined
}

function num(v: unknown): number | null {
  const n = typeof v === 'number' ? v : typeof v === 'string' ? Number(v) : null
  return n != null && Number.isFinite(n) ? n : null
}
