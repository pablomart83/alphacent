import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import {
  EmptyState,
  ErrorState,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { cn, formatCurrency, formatNumber } from '@/lib/utils'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import { BarChart3 } from 'lucide-react'

type Period = '1M' | '3M' | '6M' | '1Y' | 'ALL'
const PERIODS: Period[] = ['1M', '3M', '6M', '1Y', 'ALL']

interface TCAPayload {
  slippage_by_symbol: Array<{ symbol: string; avg_slippage_bps: number; count: number; total_shortfall: number }>
  slippage_by_hour: Array<{ day: string; hour: number; avg_slippage: number }>
  slippage_by_size: Array<{ size_bucket: string; avg_slippage_bps: number; count: number }>
  implementation_shortfall: Array<{ symbol: string; shortfall_bps: number; shortfall_dollars: number; count: number }>
  total_shortfall_dollars: number
  total_shortfall_bps: number
  fill_rate_buckets: Array<{ bucket: string; count: number; pct: number }>
  cost_as_pct_of_alpha: number
  execution_quality_trend: Array<{ date: string; avg_slippage_bps: number; fill_rate: number }>
  per_asset_class: Array<{ asset_class: string; avg_slippage_bps: number; fill_rate: number; count: number }>
  worst_executions: Array<{ symbol: string; strategy_name: string; shortfall_bps: number; shortfall_dollars: number; filled_at: string }>
}

function useTCA(period: Period) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<TCAPayload>({
    queryKey: ['tca', mode, period],
    queryFn: () => api.get<TCAPayload>('/analytics/tca', { mode, period }),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })
}

const tileClass =
  'flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)] px-2.5 py-2'

/**
 * TCATab — server-side Transaction Cost Analysis from /analytics/tca.
 * Covers: implementation shortfall, cost as % of alpha, slippage by symbol,
 * execution quality trend, per-asset-class breakdown, worst executions.
 */
export function TCATab() {
  const [period, setPeriod] = useState<Period>('3M')
  const query = useTCA(period)

  if (query.isError) {
    const info = classifyError(query.error, 'TCA')
    return (
      <ErrorState
        title="Couldn't load TCA"
        message={info.message}
        onRetry={() => query.refetch()}
      />
    )
  }

  const d = query.data

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)]">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0">
        <span className="text-[11px] text-[var(--text-2)]">Period</span>
        <Select value={period} onValueChange={(v) => setPeriod(v as Period)}>
          <SelectTrigger size="sm" className="h-7 min-w-[80px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PERIODS.map((p) => (
              <SelectItem key={p} value={p}>{p}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Headline tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 p-3 shrink-0">
        <Tile label="Total shortfall">
          {query.isLoading ? (
            <Skeleton className="h-5 w-20" />
          ) : (
            <span className={cn('mono tabular-nums text-[14px] font-semibold', (d?.total_shortfall_dollars ?? 0) > 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--pnl-up)]')}>
              {formatCurrency(d?.total_shortfall_dollars ?? 0, { signed: true, precision: 0 })}
            </span>
          )}
        </Tile>
        <Tile label="Shortfall (bps)">
          {query.isLoading ? (
            <Skeleton className="h-5 w-16" />
          ) : (
            <span className={cn('mono tabular-nums text-[14px] font-semibold', (d?.total_shortfall_bps ?? 0) > 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--pnl-up)]')}>
              {formatNumber(d?.total_shortfall_bps ?? 0, 1)} bps
            </span>
          )}
        </Tile>
        <Tile label="Cost as % of alpha">
          {query.isLoading ? (
            <Skeleton className="h-5 w-16" />
          ) : (
            <span className={cn('mono tabular-nums text-[14px] font-semibold', (d?.cost_as_pct_of_alpha ?? 0) > 5 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-0)]')}>
              {formatNumber(d?.cost_as_pct_of_alpha ?? 0, 2)}%
            </span>
          )}
        </Tile>
        <Tile label="Symbols analysed">
          {query.isLoading ? (
            <Skeleton className="h-5 w-12" />
          ) : (
            <span className="mono tabular-nums text-[14px] font-semibold text-[var(--text-0)]">
              {d?.slippage_by_symbol?.length ?? 0}
            </span>
          )}
        </Tile>
      </div>

      {/* Execution quality trend */}
      {(d?.execution_quality_trend?.length ?? 0) > 0 && (
        <div className="px-3 pb-3 shrink-0">
          <Section title="Execution quality trend">
            <div className="h-[200px]">
              <ResponsiveContainer>
                <LineChart data={d!.execution_quality_trend} margin={{ top: 4, right: 12, bottom: 2, left: -8 }}>
                  <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
                  <XAxis dataKey="date" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'var(--border-subtle)' }} tickLine={false} minTickGap={28} />
                  <YAxis yAxisId="bps" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={36} tickFormatter={(v: number) => `${v.toFixed(1)}`} />
                  <YAxis yAxisId="rate" orientation="right" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={36} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                  <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border-subtle)', fontSize: 11, borderRadius: 3 }} />
                  <Line yAxisId="bps" type="monotone" dataKey="avg_slippage_bps" name="Slippage (bps)" stroke="var(--pnl-down)" strokeWidth={1.5} dot={false} />
                  <Line yAxisId="rate" type="monotone" dataKey="fill_rate" name="Fill rate %" stroke="var(--pnl-up)" strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </Section>
        </div>
      )}

      {/* Slippage by symbol + implementation shortfall */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 px-3 pb-3 shrink-0">
        <Section title="Slippage by symbol (bps)">
          {query.isLoading ? (
            <Skeleton variant="chart" className="h-[220px]" />
          ) : !d?.slippage_by_symbol?.length ? (
            <EmptyState icon={BarChart3} title="No symbol slippage" description="Needs filled orders with expected-price data." className="py-6" />
          ) : (
            <div style={{ height: Math.max(220, d.slippage_by_symbol.slice(0, 15).length * 22 + 40) }}>
              <ResponsiveContainer>
                <BarChart data={d.slippage_by_symbol.slice(0, 15)} layout="vertical" margin={{ top: 4, right: 48, bottom: 2, left: 8 }}>
                  <XAxis type="number" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'var(--border-subtle)' }} tickLine={false} tickFormatter={(v: number) => `${v.toFixed(1)}`} />
                  <YAxis dataKey="symbol" type="category" width={60} tick={{ fill: 'var(--text-2)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} />
                  <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border-subtle)', fontSize: 11, borderRadius: 3 }} formatter={(v) => typeof v === 'number' ? [`${v.toFixed(1)} bps`, 'Avg slippage'] : ['—', 'Avg slippage']} />
                  <Bar dataKey="avg_slippage_bps" radius={[0, 2, 2, 0]}>
                    {d.slippage_by_symbol.slice(0, 15).map((r, i) => (
                      <Cell key={i} fill={r.avg_slippage_bps > 0 ? 'var(--pnl-down)' : 'var(--pnl-up)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>
        <Section title="Implementation shortfall by symbol">
          {query.isLoading ? (
            <Skeleton variant="chart" className="h-[220px]" />
          ) : !d?.implementation_shortfall?.length ? (
            <EmptyState icon={BarChart3} title="No shortfall data" description="Shortfall requires expected-price on filled orders." className="py-6" />
          ) : (
            <div className="overflow-auto max-h-[280px]">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
                    <th className="text-left px-2 py-1">Symbol</th>
                    <th className="text-right px-2 py-1">Shortfall $</th>
                    <th className="text-right px-2 py-1">Shortfall bps</th>
                    <th className="text-right px-2 py-1">Fills</th>
                  </tr>
                </thead>
                <tbody>
                  {d.implementation_shortfall.map((r) => (
                    <tr key={r.symbol} className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                      <td className="px-2 py-1 mono font-medium">{r.symbol}</td>
                      <td className={cn('px-2 py-1 text-right mono tabular-nums', r.shortfall_dollars > 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--pnl-up)]')}>
                        {formatCurrency(r.shortfall_dollars, { signed: true, precision: 0 })}
                      </td>
                      <td className={cn('px-2 py-1 text-right mono tabular-nums', r.shortfall_bps > 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--pnl-up)]')}>
                        {r.shortfall_bps > 0 ? '+' : ''}{formatNumber(r.shortfall_bps, 1)} bps
                      </td>
                      <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">{r.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>

      {/* Per asset class */}
      {(d?.per_asset_class?.length ?? 0) > 0 && (
        <div className="px-3 pb-3 shrink-0">
          <Section title="Per asset class">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
              {d!.per_asset_class.map((ac) => (
                <div key={ac.asset_class} className="rounded-[3px] bg-[var(--bg-2)] p-2 text-[10px]">
                  <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{ac.asset_class}</div>
                  <div className="mt-1 flex items-baseline gap-2">
                    <span className={cn('mono tabular-nums text-[13px] font-semibold', ac.avg_slippage_bps > 5 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-0)]')}>
                      {formatNumber(ac.avg_slippage_bps, 1)} bps
                    </span>
                  </div>
                  <div className="text-[var(--text-3)] mono">{formatNumber(ac.fill_rate, 1)}% fill · {ac.count} orders</div>
                </div>
              ))}
            </div>
          </Section>
        </div>
      )}
    </div>
  )
}

function Tile({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className={tileClass}>
      <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{label}</span>
      {children}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-[4px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <SectionLabel>{title}</SectionLabel>
      {children}
    </div>
  )
}
