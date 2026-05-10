import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { ChevronDown, ChevronUp } from 'lucide-react'
import { Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn, formatNumber } from '@/lib/utils'
import type { StressScenario } from '../useResearchData'

interface StressScenarioCardProps {
  scenario: StressScenario
  expanded: boolean
  onToggle: () => void
}

export function StressScenarioCard({
  scenario,
  expanded,
  onToggle,
}: StressScenarioCardProps) {
  const { name, start_date, end_date, spy_return_pct, portfolio_simulated_return_pct } =
    scenario
  const combined = scenario.spy_curve.map((p, i) => ({
    date: p.date,
    spy: p.value,
    portfolio: scenario.portfolio_curve[i]?.value ?? null,
  }))

  return (
    <Card padding="sm" className="flex flex-col gap-2">
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <SectionLabel className="mb-0">{name}</SectionLabel>
          <div className="text-[10px] text-[var(--text-3)] mono">
            {start_date} → {end_date}
          </div>
        </div>
        <button
          type="button"
          onClick={onToggle}
          className="inline-flex items-center gap-1 text-[10px] text-[var(--text-2)] hover:text-[var(--text-0)]"
          aria-expanded={expanded}
        >
          {expanded ? (
            <>
              Collapse <ChevronUp className="h-3 w-3" />
            </>
          ) : (
            <>
              Expand <ChevronDown className="h-3 w-3" />
            </>
          )}
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 text-[10px]">
        <Stat label="SPY" value={`${formatNumber(spy_return_pct, 2)}%`} tone={spy_return_pct >= 0 ? 'up' : 'down'} />
        <Stat
          label="Simulated portfolio"
          value={`${formatNumber(portfolio_simulated_return_pct, 2)}%`}
          tone={portfolio_simulated_return_pct >= 0 ? 'up' : 'down'}
        />
      </div>
      {expanded && (
        <div className="h-[220px] mt-1 px-1 pt-1 pb-1 rounded-[3px] bg-[var(--bg-2)]">
          <ResponsiveContainer>
            <LineChart data={combined} margin={{ top: 4, right: 8, bottom: 2, left: -8 }}>
              <CartesianGrid stroke="var(--border-subtle)" strokeDasharray="2 4" vertical={false} />
              <XAxis
                dataKey="date"
                tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--font-mono)' }}
                axisLine={{ stroke: 'var(--border-subtle)' }}
                tickLine={false}
                minTickGap={28}
              />
              <YAxis
                tick={{ fill: 'var(--text-3)', fontSize: 9, fontFamily: 'var(--font-mono)' }}
                axisLine={false}
                tickLine={false}
                width={32}
                tickFormatter={(v: number) => formatNumber(v, 0)}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--bg-1)',
                  border: '1px solid var(--border-subtle)',
                  fontSize: 11,
                  borderRadius: 3,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 10, color: 'var(--text-2)' }} iconSize={10} />
              <Line
                type="monotone"
                dataKey="spy"
                name="SPY"
                stroke="var(--text-3)"
                strokeWidth={1.2}
                dot={false}
              />
              <Line
                type="monotone"
                dataKey="portfolio"
                name="Portfolio"
                stroke={portfolio_simulated_return_pct >= 0 ? 'var(--pnl-up)' : 'var(--pnl-down)'}
                strokeWidth={1.6}
                dot={false}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
      {!expanded && (
        <div className="text-[10px] text-[var(--text-3)] italic">
          {scenario.portfolio_simulated_return_pct >= 0
            ? 'Simulated portfolio would have held up — driven by low-beta mix.'
            : 'Simulated portfolio would have followed SPY down, scaled by portfolio beta ≈ 0.70.'}
        </div>
      )}
    </Card>
  )
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[14px] font-semibold',
          tone === 'up'
            ? 'text-[var(--pnl-up)]'
            : tone === 'down'
              ? 'text-[var(--pnl-down)]'
              : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}
