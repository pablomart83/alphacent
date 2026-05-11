import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
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
import { cn, formatNumber } from '@/lib/utils'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import { BarChart3 } from 'lucide-react'

type Period = '1M' | '3M' | '6M' | '1Y' | 'ALL'
const PERIODS: Period[] = ['1M', '3M', '6M', '1Y', 'ALL']

interface StrategyAttribution {
  strategy_id: string
  strategy_name: string
  total_return: number
  contribution_percent: number
  sharpe_ratio: number
  total_trades: number
  win_rate: number
}

interface ConvictionCalibration {
  buckets: Array<{
    range: string
    count: number
    win_rate: number
    avg_pnl: number
    expected_win_rate: number
  }>
  calibration_score: number
  message?: string
}

function useStrategyAttribution(period: Period) {
  const mode = useTradingMode((s) => s.mode)
  return useQuery<StrategyAttribution[]>({
    queryKey: ['strategy-attribution', mode, period],
    queryFn: () =>
      api.get<StrategyAttribution[]>('/analytics/strategy-attribution', { mode, period }),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })
}

function useConvictionCalibration() {
  return useQuery<ConvictionCalibration>({
    queryKey: ['conviction-calibration'],
    queryFn: () => api.get<ConvictionCalibration>('/analytics/conviction-calibration'),
    staleTime: 5 * 60_000,
  })
}

/**
 * PaperLiveAnalyticsTab — strategy-level attribution and conviction
 * calibration. Answers "which strategies are actually contributing?" and
 * "is our conviction score predictive of outcomes?".
 */
export function PaperLiveAnalyticsTab() {
  const [period, setPeriod] = useState<Period>('3M')
  const mode = useTradingMode((s) => s.mode)
  const attribution = useStrategyAttribution(period)
  const calibration = useConvictionCalibration()

  if (attribution.isError) {
    const info = classifyError(attribution.error, 'strategy attribution')
    return (
      <ErrorState
        title="Couldn't load analytics"
        message={info.message}
        onRetry={() => attribution.refetch()}
      />
    )
  }

  const rows = attribution.data ?? []
  const top15 = [...rows].sort((a, b) => Math.abs(b.total_return) - Math.abs(a.total_return)).slice(0, 15)
  const calBuckets = calibration.data?.buckets ?? []

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
        <span className="ml-auto text-[10px] text-[var(--text-3)] mono">
          {mode} · {rows.length} strategies
        </span>
      </div>

      {/* Strategy contribution bar */}
      <div className="px-3 pt-3 pb-2 shrink-0">
        <Section title={`Top 15 strategy contributors · ${mode}`}>
          {attribution.isLoading ? (
            <Skeleton variant="chart" className="h-[280px]" />
          ) : !top15.length ? (
            <EmptyState icon={BarChart3} title="No attribution data" description="Strategies need closed positions in the selected period." className="py-6" />
          ) : (
            <div style={{ height: Math.max(280, top15.length * 22 + 40) }}>
              <ResponsiveContainer>
                <BarChart data={top15} layout="vertical" margin={{ top: 4, right: 60, bottom: 2, left: 8 }}>
                  <CartesianGrid stroke="var(--border-subtle)" horizontal={false} />
                  <XAxis type="number" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'var(--border-subtle)' }} tickLine={false} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                  <YAxis dataKey="strategy_name" type="category" width={180} tick={{ fill: 'var(--text-2)', fontSize: 10 }} axisLine={false} tickLine={false} tickFormatter={(v: string) => v.length > 28 ? `${v.slice(0, 26)}…` : v} />
                  <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border-subtle)', fontSize: 11, borderRadius: 3 }} formatter={(v, name, item) => {
                    if (typeof v !== 'number') return ['—', String(name)]
                    const row = item?.payload as StrategyAttribution | undefined
                    return [`${v > 0 ? '+' : ''}${v.toFixed(2)}% · Sharpe ${formatNumber(row?.sharpe_ratio ?? 0, 2)} · ${row?.total_trades ?? 0} trades`, 'Return']
                  }} />
                  <Bar dataKey="total_return" radius={[0, 2, 2, 0]}>
                    {top15.map((r) => (
                      <Cell key={r.strategy_id} fill={r.total_return >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>
      </div>

      {/* Conviction calibration */}
      <div className="px-3 pb-3 shrink-0">
        <Section title="Conviction score calibration">
          {calibration.isLoading ? (
            <Skeleton variant="chart" className="h-[220px]" />
          ) : !calBuckets.length ? (
            <EmptyState icon={BarChart3} title="No calibration data" description="Needs closed trades with conviction scores." className="py-6" />
          ) : (
            <>
              {calibration.data?.message && (
                <div className="text-[10px] text-[var(--text-3)] mb-2">{calibration.data.message}</div>
              )}
              <div className="h-[220px]">
                <ResponsiveContainer>
                  <BarChart data={calBuckets} margin={{ top: 4, right: 12, bottom: 2, left: -8 }}>
                    <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
                    <XAxis dataKey="range" tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={{ stroke: 'var(--border-subtle)' }} tickLine={false} />
                    <YAxis tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }} axisLine={false} tickLine={false} width={36} tickFormatter={(v: number) => `${v.toFixed(0)}%`} />
                    <Tooltip contentStyle={{ background: 'var(--bg-2)', border: '1px solid var(--border-subtle)', fontSize: 11, borderRadius: 3 }} formatter={(v, name) => typeof v === 'number' ? [`${v.toFixed(1)}%`, String(name)] : ['—', String(name)]} />
                    <Bar dataKey="win_rate" name="Actual win %" radius={[2, 2, 0, 0]}>
                      {calBuckets.map((b, i) => (
                        <Cell key={i} fill={b.win_rate >= 50 ? 'var(--pnl-up)' : 'var(--pnl-down)'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
              {calibration.data?.calibration_score != null && (
                <div className="mt-1 text-[10px] text-[var(--text-3)]">
                  Calibration score:{' '}
                  <span className={cn('mono font-medium', calibration.data.calibration_score >= 0.7 ? 'text-[var(--pnl-up)]' : 'text-[var(--status-warning)]')}>
                    {formatNumber(calibration.data.calibration_score * 100, 1)}%
                  </span>
                  {' '}— measures how well conviction predicts win rate (1.0 = perfect).
                </div>
              )}
            </>
          )}
        </Section>
      </div>

      {/* Full attribution table */}
      <div className="px-3 pb-4 shrink-0">
        <Section title="Full strategy attribution">
          {attribution.isLoading ? (
            <Skeleton className="h-[200px]" />
          ) : !rows.length ? (
            <EmptyState icon={BarChart3} title="No attribution" description="No strategies with positions in this period." className="py-4" />
          ) : (
            <div className="overflow-auto max-h-[320px]">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
                    <th className="text-left px-2 py-1">Strategy</th>
                    <th className="text-right px-2 py-1">Return</th>
                    <th className="text-right px-2 py-1">Contrib %</th>
                    <th className="text-right px-2 py-1">Sharpe</th>
                    <th className="text-right px-2 py-1">Trades</th>
                    <th className="text-right px-2 py-1">Win %</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((r) => (
                    <tr key={r.strategy_id} className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                      <td className="px-2 py-1 truncate max-w-[240px]" title={r.strategy_name}>{r.strategy_name}</td>
                      <td className={cn('px-2 py-1 text-right mono tabular-nums', r.total_return > 0 ? 'text-[var(--pnl-up)]' : r.total_return < 0 ? 'text-[var(--pnl-down)]' : '')}>
                        {r.total_return > 0 ? '+' : ''}{formatNumber(r.total_return, 2)}%
                      </td>
                      <td className={cn('px-2 py-1 text-right mono tabular-nums', r.contribution_percent > 0 ? 'text-[var(--pnl-up)]' : r.contribution_percent < 0 ? 'text-[var(--pnl-down)]' : '')}>
                        {r.contribution_percent > 0 ? '+' : ''}{formatNumber(r.contribution_percent, 1)}%
                      </td>
                      <td className="px-2 py-1 text-right mono tabular-nums">{formatNumber(r.sharpe_ratio, 2)}</td>
                      <td className="px-2 py-1 text-right mono tabular-nums">{r.total_trades}</td>
                      <td className="px-2 py-1 text-right mono tabular-nums">{formatNumber(r.win_rate, 1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Section>
      </div>
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
