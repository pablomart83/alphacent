import { useMemo } from 'react'
import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ColumnDef } from '@tanstack/react-table'
import { SectionLabel } from '@/components/layout'
import { DataTable, EmptyState, ErrorState, Skeleton } from '@/components/primitives'
import { Layers } from 'lucide-react'
import { cn, formatNumber } from '@/lib/utils'
import { classifyError } from '@/lib/errors'
import type { PerformanceAttributionPayload, SectorAttribution } from '../useResearchData'

interface SectorAttributionPanelProps {
  data: PerformanceAttributionPayload | undefined
  loading?: boolean
  error?: unknown
  onRetry?: () => void
}

/**
 * Sector attribution — Brinson decomposition.
 *   • Stacked horizontal bar per sector: allocation / selection / interaction.
 *   • Sortable table with the raw values.
 *   • Cumulative-effects area chart if the backend returned a timeseries.
 */
export function SectorAttributionPanel({
  data,
  loading,
  error,
  onRetry,
}: SectorAttributionPanelProps) {
  const sectors = data?.sectors ?? []
  const cumulative = data?.cumulative_effects ?? []

  const maxAbsTotal = useMemo(() => {
    if (!sectors.length) return 1
    return (
      Math.max(
        1e-6,
        ...sectors.map((s) =>
          Math.abs(s.allocation_effect) +
          Math.abs(s.selection_effect) +
          Math.abs(s.interaction_effect),
        ),
      )
    )
  }, [sectors])

  const columns = useMemo<ColumnDef<SectorAttribution>[]>(
    () => [
      {
        id: 'sector',
        accessorKey: 'sector',
        header: () => <span>Sector</span>,
        size: 160,
        cell: ({ getValue }) => (
          <span className="truncate" title={String(getValue())}>
            {String(getValue())}
          </span>
        ),
      },
      {
        id: 'portfolio_weight',
        accessorKey: 'portfolio_weight',
        header: () => <span className="text-right block w-full">Port. wt</span>,
        size: 80,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()) * 100, 1)}%
          </span>
        ),
      },
      {
        id: 'benchmark_weight',
        accessorKey: 'benchmark_weight',
        header: () => <span className="text-right block w-full">Bench wt</span>,
        size: 80,
        cell: ({ getValue }) => (
          <span className="mono tabular-nums text-right block">
            {formatNumber(Number(getValue()) * 100, 1)}%
          </span>
        ),
      },
      {
        id: 'allocation_effect',
        accessorKey: 'allocation_effect',
        header: () => <span className="text-right block w-full">Alloc</span>,
        size: 80,
        cell: ({ getValue }) => signedPct(Number(getValue())),
      },
      {
        id: 'selection_effect',
        accessorKey: 'selection_effect',
        header: () => <span className="text-right block w-full">Select</span>,
        size: 80,
        cell: ({ getValue }) => signedPct(Number(getValue())),
      },
      {
        id: 'interaction_effect',
        accessorKey: 'interaction_effect',
        header: () => <span className="text-right block w-full">Interact</span>,
        size: 80,
        cell: ({ getValue }) => signedPct(Number(getValue())),
      },
      {
        id: 'total_contribution',
        accessorKey: 'total_contribution',
        header: () => <span className="text-right block w-full">Total</span>,
        size: 80,
        cell: ({ getValue }) => signedPct(Number(getValue()), 'font-semibold'),
      },
    ],
    [],
  )

  if (error) {
    const info = classifyError(error, 'sector attribution')
    return (
      <ErrorState
        title="Couldn't load sector attribution"
        message={info.message}
        onRetry={onRetry}
      />
    )
  }

  if (loading && !sectors.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Sector attribution</SectionLabel>
        <Skeleton variant="chart" />
      </section>
    )
  }

  if (!sectors.length) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Sector attribution</SectionLabel>
        <EmptyState
          icon={Layers}
          title="No sector attribution available"
          description="Sector attribution is computed once positions are classified into sector groups."
          className="py-8"
        />
      </section>
    )
  }

  return (
    <section className="space-y-3">
      <div className="space-y-1.5">
        <SectionLabel>Sector attribution · stacked effects</SectionLabel>
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-3 py-2 space-y-1.5">
          {sectors.map((s) => (
            <SectorBar key={s.sector} row={s} maxAbs={maxAbsTotal} />
          ))}
          <div className="flex items-center gap-3 pt-1.5 mt-1.5 border-t border-[var(--border-subtle)] text-[9px] uppercase tracking-wider text-[var(--text-3)]">
            <LegendChip color="var(--accent-primary)" label="Allocation" />
            <LegendChip color="var(--regime-up)" label="Selection" />
            <LegendChip color="var(--accent-ticker)" label="Interaction" />
          </div>
        </div>
      </div>

      <div className="space-y-1.5">
        <SectionLabel>Sector attribution · detail</SectionLabel>
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] max-h-[300px] overflow-hidden">
          <DataTable
            data={sectors}
            columns={columns}
            rowKey={(r) => r.sector}
            loading={loading}
          />
        </div>
      </div>

      {cumulative.length > 1 && (
        <div className="space-y-1.5">
          <SectionLabel>Cumulative effects over time</SectionLabel>
          <div className="h-[240px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 pt-2 pb-1">
            <ResponsiveContainer>
              <AreaChart data={cumulative} margin={{ top: 4, right: 12, bottom: 2, left: -4 }}>
                <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
                <XAxis
                  dataKey="date"
                  tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  axisLine={{ stroke: 'var(--border-subtle)' }}
                  tickLine={false}
                  minTickGap={28}
                />
                <YAxis
                  tick={{ fill: 'var(--text-3)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                  axisLine={false}
                  tickLine={false}
                  width={48}
                  tickFormatter={(v: number) => `${(v * 100).toFixed(1)}%`}
                />
                <Tooltip
                  contentStyle={{
                    background: 'var(--bg-2)',
                    border: '1px solid var(--border-subtle)',
                    fontSize: 11,
                    borderRadius: 3,
                  }}
                  formatter={(v, name) =>
                    typeof v === 'number'
                      ? [`${(v * 100).toFixed(2)}%`, String(name)]
                      : ['—', String(name)]
                  }
                />
                <Legend
                  wrapperStyle={{ fontSize: 10, color: 'var(--text-2)' }}
                  iconSize={10}
                />
                <Area
                  type="monotone"
                  dataKey="allocation"
                  stackId="1"
                  stroke="var(--accent-primary)"
                  fill="color-mix(in oklab, var(--accent-primary) 45%, transparent)"
                />
                <Area
                  type="monotone"
                  dataKey="selection"
                  stackId="1"
                  stroke="var(--regime-up)"
                  fill="color-mix(in oklab, var(--regime-up) 45%, transparent)"
                />
                <Area
                  type="monotone"
                  dataKey="interaction"
                  stackId="1"
                  stroke="var(--accent-ticker)"
                  fill="color-mix(in oklab, var(--accent-ticker) 45%, transparent)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}
    </section>
  )
}

function SectorBar({ row, maxAbs }: { row: SectorAttribution; maxAbs: number }) {
  const { allocation_effect: a, selection_effect: s, interaction_effect: i, sector, total_contribution: total } = row
  const scale = (v: number) => (Math.abs(v) / maxAbs) * 100
  return (
    <div className="grid grid-cols-[160px_1fr_80px] items-center gap-2 text-[10px]">
      <span className="truncate text-[var(--text-1)]" title={sector}>
        {sector}
      </span>
      <div className="relative h-2 bg-[var(--bg-2)] rounded-[1px] overflow-hidden">
        {/* Stacked from 50% baseline; positives to the right, negatives to the left. */}
        <StackRectNeg value={a} color="var(--accent-primary)" scale={scale} offset={0} />
        <StackRectNeg
          value={s}
          color="var(--regime-up)"
          scale={scale}
          offset={a < 0 ? scale(a) : 0}
        />
        <StackRectNeg
          value={i}
          color="var(--accent-ticker)"
          scale={scale}
          offset={(a < 0 ? scale(a) : 0) + (s < 0 ? scale(s) : 0)}
        />
        <StackRectPos value={a} color="var(--accent-primary)" scale={scale} offset={0} />
        <StackRectPos
          value={s}
          color="var(--regime-up)"
          scale={scale}
          offset={a > 0 ? scale(a) : 0}
        />
        <StackRectPos
          value={i}
          color="var(--accent-ticker)"
          scale={scale}
          offset={(a > 0 ? scale(a) : 0) + (s > 0 ? scale(s) : 0)}
        />
        <div
          className="absolute inset-y-0"
          style={{ left: '50%', width: 1, backgroundColor: 'var(--border-subtle)' }}
        />
      </div>
      <span
        className={cn(
          'mono tabular-nums text-right',
          total > 0 ? 'text-[var(--pnl-up)]' : total < 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-2)]',
        )}
      >
        {total > 0 ? '+' : ''}
        {formatNumber(total * 100, 2)}%
      </span>
    </div>
  )
}

function StackRectPos({
  value,
  color,
  scale,
  offset,
}: {
  value: number
  color: string
  scale: (v: number) => number
  offset: number
}) {
  if (value <= 0) return null
  return (
    <span
      className="absolute top-0 bottom-0"
      style={{ left: `${50 + offset}%`, width: `${scale(value)}%`, backgroundColor: color }}
    />
  )
}

function StackRectNeg({
  value,
  color,
  scale,
  offset,
}: {
  value: number
  color: string
  scale: (v: number) => number
  offset: number
}) {
  if (value >= 0) return null
  return (
    <span
      className="absolute top-0 bottom-0"
      style={{
        right: `${50 + offset}%`,
        width: `${scale(value)}%`,
        backgroundColor: color,
      }}
    />
  )
}

function LegendChip({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-1">
      <span className="h-1.5 w-3 rounded-[1px]" style={{ backgroundColor: color }} />
      {label}
    </span>
  )
}

function signedPct(v: number, extra = '') {
  return (
    <span
      className={cn(
        'mono tabular-nums text-right block',
        extra,
        v > 0 ? 'text-[var(--pnl-up)]' : v < 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-2)]',
      )}
    >
      {v > 0 ? '+' : ''}
      {(v * 100).toFixed(2)}%
    </span>
  )
}
