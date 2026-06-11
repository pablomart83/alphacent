/**
 * IntelOverview — shown in the right panel when no finding is selected.
 * Shows: severity breakdown bar, category distribution, top-priority list.
 */
import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import { AlertTriangle, CheckCircle, TrendingUp } from 'lucide-react'
import type { IntelFinding } from './useIntelData'
import { categoryLabel, severityColor } from './useIntelData'

interface Props {
  findings: IntelFinding[]
  onSelect: (id: string) => void
}

const SEVERITIES = ['P0', 'P1', 'P2', 'opportunity'] as const
const SEV_LABELS: Record<string, string> = {
  P0: 'Critical',
  P1: 'High',
  P2: 'Medium',
  opportunity: 'Opportunity',
}

const CATEGORIES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']

export function IntelOverview({ findings, onSelect }: Props) {
  const open = useMemo(() => findings.filter((f) => f.status === 'open'), [findings])

  // Category breakdown
  const catData = useMemo(
    () =>
      CATEGORIES.map((cat) => {
        const items = open.filter((f) => f.category === cat)
        const p0 = items.filter((f) => f.severity === 'P0').length
        const p1 = items.filter((f) => f.severity === 'P1').length
        const p2 = items.filter((f) => f.severity === 'P2').length
        const opp = items.filter((f) => f.severity === 'opportunity').length
        return { cat, label: categoryLabel(cat), total: items.length, p0, p1, p2, opp }
      }).filter((d) => d.total > 0),
    [open],
  )

  // Top priority findings (P0 first, then P1, sorted by occurrence_count)
  const topFindings = useMemo(
    () =>
      [...open]
        .sort((a, b) => {
          const sevScore = (s: string) =>
            s === 'P0' ? 0 : s === 'P1' ? 1 : s === 'P2' ? 2 : 3
          const diff = sevScore(a.severity) - sevScore(b.severity)
          if (diff !== 0) return diff
          return (b.occurrence_count ?? 0) - (a.occurrence_count ?? 0)
        })
        .slice(0, 8),
    [open],
  )

  if (open.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-3 text-[var(--text-3)]">
        <CheckCircle className="h-10 w-10 opacity-30" />
        <p className="text-[12px]">No open findings</p>
        <p className="text-[10px]">Run analysis to check system health</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 overflow-y-auto p-4 gap-5">
      {/* Severity summary row */}
      <div className="grid grid-cols-4 gap-2">
        {SEVERITIES.map((sev) => {
          const count = open.filter((f) => f.severity === sev).length
          return (
            <div
              key={sev}
              className="flex flex-col gap-0.5 px-3 py-2.5 rounded border border-[var(--border-subtle)] bg-[var(--bg-1)]"
            >
              <span
                className="text-xl font-bold mono tabular-nums"
                style={{ color: count > 0 ? severityColor(sev) : 'var(--text-3)' }}
              >
                {count}
              </span>
              <span className="text-[9px] text-[var(--text-3)] uppercase tracking-wide">
                {SEV_LABELS[sev]}
              </span>
            </div>
          )
        })}
      </div>

      {/* Category distribution bar chart */}
      {catData.length > 0 && (
        <div>
          <p className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)] mb-2">
            Findings by category
          </p>
          <div style={{ height: 120 }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart
                data={catData}
                margin={{ top: 0, right: 0, left: -28, bottom: 0 }}
                barSize={18}
              >
                <XAxis
                  dataKey="cat"
                  tick={{ fontSize: 10, fill: 'var(--text-3)' }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 9, fill: 'var(--text-3)' }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                />
                <Tooltip
                  cursor={{ fill: 'rgba(255,255,255,0.04)' }}
                  contentStyle={{
                    background: 'var(--bg-2)',
                    border: '1px solid var(--border-default)',
                    borderRadius: 4,
                    fontSize: 11,
                    color: 'var(--text-1)',
                  }}
                  formatter={(value: any, _name: any) => [
                    `${value} findings`,
                    '',
                  ]}
                  labelFormatter={(label) => `Category ${label} — ${categoryLabel(label)}`}
                />
                <Bar dataKey="p0" stackId="a" fill={severityColor('P0')} radius={[0, 0, 0, 0]} />
                <Bar dataKey="p1" stackId="a" fill={severityColor('P1')} />
                <Bar dataKey="p2" stackId="a" fill={severityColor('P2')} />
                <Bar dataKey="opp" stackId="a" fill={severityColor('opportunity')} radius={[2, 2, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          {/* Category legend */}
          <div className="flex flex-wrap gap-x-3 gap-y-1 mt-1">
            {catData.map((d) => (
              <span key={d.cat} className="text-[9px] text-[var(--text-3)]">
                <span className="text-[var(--text-2)] font-medium">{d.cat}</span> {d.label} ({d.total})
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Priority list */}
      <div>
        <div className="flex items-center gap-2 mb-2">
          <AlertTriangle className="h-3 w-3 text-[var(--status-warning)]" />
          <p className="text-[9px] font-semibold uppercase tracking-widest text-[var(--text-3)]">
            Top priority findings
          </p>
        </div>
        <div className="space-y-1">
          {topFindings.map((f, i) => (
            <button
              key={f.id}
              type="button"
              onClick={() => onSelect(f.id)}
              className="w-full text-left flex items-start gap-2.5 px-3 py-2 rounded border border-[var(--border-subtle)] hover:border-[var(--border-default)] hover:bg-[var(--bg-hover)] transition-all group"
            >
              {/* Rank */}
              <span className="text-[10px] text-[var(--text-3)] mono w-4 shrink-0 mt-0.5">
                {i + 1}
              </span>
              {/* Severity dot */}
              <span
                className="w-2 h-2 rounded-full shrink-0 mt-1"
                style={{ background: severityColor(f.severity) }}
              />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span
                    className="text-[9px] font-semibold mono"
                    style={{ color: severityColor(f.severity) }}
                  >
                    {f.severity}
                  </span>
                  <span className="text-[9px] text-[var(--text-3)]">{f.check_id}</span>
                  <span className="text-[9px] text-[var(--text-3)]">·</span>
                  <span className="text-[9px] text-[var(--text-3)]">{categoryLabel(f.category)}</span>
                  {f.occurrence_count > 1 && (
                    <span className="text-[9px] text-[var(--text-3)] ml-auto">
                      {f.occurrence_count}×
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-[var(--text-1)] leading-tight truncate group-hover:text-[var(--text-0)]">
                  {f.title.replace(/^[A-H]\d+:\s*/, '')}
                </p>
              </div>
              <TrendingUp className="h-3 w-3 text-[var(--text-3)] shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity" />
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
