import { useMemo, useState } from 'react'
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
import { ParentSize } from '@visx/responsive'
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
import { cn, formatTimestamp } from '@/lib/utils'
import { useOrders } from '../useBookData'
import {
  computeExecutionAnalytics,
  EXECUTION_PERIODS,
  type ExecutionPeriod,
} from './computeMetrics'
import { SlippageTrendChart } from './SlippageTrendChart'
import { SlippageHeatmap } from './SlippageHeatmap'
import { BarChart3 } from 'lucide-react'

const tileClass =
  'flex flex-col gap-0.5 rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)] px-2.5 py-2'

export function ExecutionTab() {
  const [period, setPeriod] = useState<ExecutionPeriod>('1M')
  const ordersQuery = useOrders({ limit: 2000 })
  const orders = ordersQuery.data?.orders ?? []

  const analytics = useMemo(
    () => computeExecutionAnalytics(orders, period),
    [orders, period],
  )

  if (ordersQuery.isError) {
    const info = classifyError(ordersQuery.error, 'execution analytics')
    return (
      <ErrorState
        title="Couldn't load execution analytics"
        message={info.message}
        onRetry={() => ordersQuery.refetch()}
      />
    )
  }

  const {
    tiles,
    trend,
    byStrategy,
    heatmap,
    rejections,
    fillBuckets,
    worst,
    byAssetClass,
  } = analytics

  return (
    <div className="flex flex-col h-full min-h-0 overflow-auto bg-[var(--bg-0)]">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)] shrink-0">
        <span className="text-[11px] text-[var(--text-2)]">Period</span>
        <Select value={period} onValueChange={(v) => setPeriod(v as ExecutionPeriod)}>
          <SelectTrigger size="sm" className="h-7 min-w-[80px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {EXECUTION_PERIODS.map((p) => (
              <SelectItem key={p} value={p}>
                {p}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="ml-auto text-[10px] text-[var(--text-3)] mono">
          {ordersQuery.isLoading ? 'Loading…' : `${orders.length} orders analysed`}
        </span>
      </div>

      {/* Tiles */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2 p-3 shrink-0">
        <Tile label="Filled">
          <span className="mono tabular-nums text-[14px] text-[var(--text-0)] font-semibold">
            {tiles.filledCount.toLocaleString('en-US')}
          </span>
        </Tile>
        <Tile label="Avg slippage">
          {tiles.avgSlippageBps == null ? (
            <span className="text-[var(--text-3)] mono">—</span>
          ) : (
            <SlippageValue bps={tiles.avgSlippageBps} />
          )}
        </Tile>
        <Tile label="Fill rate">
          <PctValue pct={tiles.fillRatePct} goodAbove={95} />
        </Tile>
        <Tile label="Avg fill time">
          {tiles.avgFillTimeSec == null ? (
            <span className="text-[var(--text-3)] mono">—</span>
          ) : (
            <span className="mono tabular-nums text-[14px] text-[var(--text-0)] font-semibold">
              {tiles.avgFillTimeSec < 60
                ? `${tiles.avgFillTimeSec.toFixed(1)}s`
                : `${(tiles.avgFillTimeSec / 60).toFixed(1)}m`}
            </span>
          )}
        </Tile>
        <Tile label="Rejection rate">
          <PctValue pct={tiles.rejectionRatePct} invert goodBelow={5} />
        </Tile>
        <Tile label="Shortfall">
          {tiles.implementationShortfallBps == null ? (
            <span className="text-[var(--text-3)] mono">—</span>
          ) : (
            <span className="mono tabular-nums text-[14px] text-[var(--text-0)] font-semibold">
              {tiles.implementationShortfallBps.toFixed(1)} bps
            </span>
          )}
        </Tile>
      </div>

      {/* Sample coverage strip */}
      {tiles.filledCount > 0 && (
        <div className="px-3 pb-1 text-[10px] text-[var(--text-3)]">
          Slippage computed from{' '}
          <span
            style={{
              color:
                tiles.sampleCoveragePct >= 50
                  ? 'var(--text-1)'
                  : 'var(--status-warning)',
            }}
          >
            {tiles.sampleCoveragePct.toFixed(0)}%
          </span>{' '}
          of filled orders — rest lack expected-price data on eToro side.
        </div>
      )}

      {/* Row: trend + heatmap */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 p-3 shrink-0">
        <Section title="Slippage trend (bps)">
          {ordersQuery.isLoading ? (
            <Skeleton variant="chart" className="h-[180px]" />
          ) : (
            <SlippageTrendChart data={trend} />
          )}
        </Section>
        <Section title="By hour × day (UTC)">
          {ordersQuery.isLoading ? (
            <Skeleton variant="chart" className="h-[180px]" />
          ) : (
            <div className="h-[180px]">
              <ParentSize>
                {({ width }: { width: number }) =>
                  width > 0 ? <SlippageHeatmap cells={heatmap} width={width} /> : null
                }
              </ParentSize>
            </div>
          )}
        </Section>
      </div>

      {/* Row: by-strategy + rejections */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 px-3 pb-3 shrink-0">
        <Section title="Slippage by strategy">
          {byStrategy.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="No per-strategy slippage"
              description="Fills with expected-price data feed this chart."
              className="py-6"
            />
          ) : (
            <div style={{ width: '100%', height: 220 }}>
              <ResponsiveContainer>
                <BarChart
                  data={byStrategy}
                  layout="vertical"
                  margin={{ top: 4, right: 16, left: 0, bottom: 0 }}
                >
                  <CartesianGrid stroke="var(--border-subtle)" horizontal={false} />
                  <XAxis
                    type="number"
                    tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                    stroke="var(--border-subtle)"
                  />
                  <YAxis
                    dataKey="strategy"
                    type="category"
                    tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                    stroke="var(--border-subtle)"
                    width={140}
                    tickFormatter={(v: string) => (v.length > 22 ? `${v.slice(0, 22)}…` : v)}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-2)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 3,
                      fontSize: 11,
                      color: 'var(--text-0)',
                    }}
                    formatter={(v, _name, p) => [
                      typeof v === 'number' ? `${v.toFixed(1)} bps` : '—',
                      `${(p as any)?.payload?.count ?? 0} fills`,
                    ]}
                  />
                  <Bar dataKey="avgBps">
                    {byStrategy.map((row, i) => (
                      <Cell
                        key={i}
                        fill={row.avgBps > 0 ? 'var(--pnl-down)' : 'var(--pnl-up)'}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>
        <Section title="Rejection reasons">
          {rejections.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="No rejections in range"
              description="Clean execution — all attempted orders either filled or are still pending."
              className="py-6"
            />
          ) : (
            <div style={{ width: '100%', height: 220 }}>
              <ResponsiveContainer>
                <BarChart data={rejections} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="var(--border-subtle)" vertical={false} />
                  <XAxis
                    dataKey="reason"
                    tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                    stroke="var(--border-subtle)"
                    interval={0}
                    angle={-15}
                    height={56}
                    textAnchor="end"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                    stroke="var(--border-subtle)"
                    width={32}
                    allowDecimals={false}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--bg-2)',
                      border: '1px solid var(--border-default)',
                      borderRadius: 3,
                      fontSize: 11,
                      color: 'var(--text-0)',
                    }}
                  />
                  <Bar dataKey="count" fill="var(--status-warning)" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </Section>
      </div>

      {/* Row: fill buckets + asset class */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-2 px-3 pb-3 shrink-0">
        <Section title="Fill-time distribution">
          <div className="grid grid-cols-4 gap-1.5">
            {fillBuckets.map((b) => (
              <div key={b.label} className="rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)] p-2">
                <div className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{b.label}</div>
                <div className="mt-0.5 mono tabular-nums text-[var(--text-0)] text-[13px] font-semibold">
                  {b.count.toLocaleString('en-US')}
                </div>
                <div className="mono text-[10px] text-[var(--text-3)]">
                  {b.pct.toFixed(1)}%
                </div>
                <div className="mt-1 h-1 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
                  <div
                    className="h-full bg-[var(--accent-primary)]"
                    style={{ width: `${b.pct}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </Section>
        <Section title="By asset class">
          <div className="grid grid-cols-2 gap-1.5">
            {byAssetClass.map((ac) => (
              <div
                key={ac.assetClass}
                className="rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-subtle)] p-2"
              >
                <div className="flex items-center justify-between">
                  <span className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">{ac.assetClass}</span>
                  <span className="text-[10px] mono text-[var(--text-3)]">
                    {ac.filledCount}/{ac.totalCount}
                  </span>
                </div>
                <div className="mt-0.5 flex items-baseline gap-2">
                  <span className="mono tabular-nums text-[var(--text-0)] text-[13px] font-semibold">
                    {ac.fillRatePct.toFixed(1)}%
                  </span>
                  {ac.avgBps != null && (
                    <span
                      className="mono tabular-nums text-[10px]"
                      style={{
                        color:
                          Math.abs(ac.avgBps) < 3
                            ? 'var(--text-2)'
                            : ac.avgBps > 0
                              ? 'var(--pnl-down)'
                              : 'var(--pnl-up)',
                      }}
                    >
                      {ac.avgBps >= 0 ? '+' : ''}
                      {ac.avgBps.toFixed(1)} bps
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* Worst executions */}
      <div className="px-3 pb-4 shrink-0">
        <Section title="Worst 20 executions">
          {worst.length === 0 ? (
            <EmptyState
              icon={BarChart3}
              title="No slippage data"
              description="Orders need expected-price + filled-price to rank."
              className="py-4"
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-[10px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
                    <th className="text-left px-2 py-1">Symbol</th>
                    <th className="text-left px-2 py-1">Strategy</th>
                    <th className="text-right px-2 py-1">Expected</th>
                    <th className="text-right px-2 py-1">Filled</th>
                    <th className="text-right px-2 py-1">Shortfall</th>
                    <th className="text-left px-2 py-1">When</th>
                  </tr>
                </thead>
                <tbody>
                  {worst.map((w) => (
                    <tr
                      key={w.row.id}
                      className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]"
                    >
                      <td className="px-2 py-1 mono font-semibold">{w.row.symbol}</td>
                      <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[220px]">
                        {w.row.strategy_name || '—'}
                      </td>
                      <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                        {w.row.expected_price ?? '—'}
                      </td>
                      <td className="px-2 py-1 text-right mono tabular-nums">
                        {w.row.filled_price ?? '—'}
                      </td>
                      <td className="px-2 py-1 text-right mono tabular-nums">
                        <span
                          style={{
                            color:
                              w.shortfallBps > 0
                                ? 'var(--pnl-down)'
                                : 'var(--pnl-up)',
                          }}
                        >
                          {w.shortfallBps >= 0 ? '+' : ''}
                          {w.shortfallBps.toFixed(1)} bps
                        </span>
                      </td>
                      <td className="px-2 py-1 text-[10px] text-[var(--text-3)]">
                        {formatTimestamp(w.row.filled_at, 'short')}
                      </td>
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

function SlippageValue({ bps }: { bps: number }) {
  const colour =
    Math.abs(bps) < 3
      ? 'text-[var(--text-0)]'
      : bps > 0
        ? 'text-[var(--pnl-down)]'
        : 'text-[var(--pnl-up)]'
  return (
    <span className={cn('mono tabular-nums text-[14px] font-semibold', colour)}>
      {bps >= 0 ? '+' : ''}
      {bps.toFixed(1)} bps
    </span>
  )
}

function PctValue({
  pct,
  invert,
  goodAbove,
  goodBelow,
}: {
  pct: number
  invert?: boolean
  goodAbove?: number
  goodBelow?: number
}) {
  let colour = 'text-[var(--text-0)]'
  if (goodAbove != null && !invert) {
    colour = pct >= goodAbove ? 'text-[var(--pnl-up)]' : pct >= goodAbove - 10 ? 'text-[var(--status-warning)]' : 'text-[var(--pnl-down)]'
  } else if (goodBelow != null && invert) {
    colour = pct <= goodBelow ? 'text-[var(--pnl-up)]' : pct <= goodBelow + 10 ? 'text-[var(--status-warning)]' : 'text-[var(--pnl-down)]'
  }
  return (
    <span className={cn('mono tabular-nums text-[14px] font-semibold', colour)}>
      {pct.toFixed(1)}%
    </span>
  )
}
