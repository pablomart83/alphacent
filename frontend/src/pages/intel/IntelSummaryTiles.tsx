import { StatTile } from '@/components/primitives'
import { formatAge } from '@/lib/utils'
import type { IntelSummary } from './useIntelData'

interface Props {
  summary: IntelSummary | undefined
  loading: boolean
}

export function IntelSummaryTiles({ summary, loading }: Props) {
  if (loading && !summary) {
    return (
      <div className="grid grid-cols-5 gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-16 rounded bg-[var(--bg-1)] animate-pulse" />
        ))}
      </div>
    )
  }

  const s = summary ?? {
    p0_open: 0,
    p1_open: 0,
    p2_open: 0,
    opportunities_open: 0,
    resolved_this_week: 0,
    last_run_at: null,
    last_run_duration_s: null,
    last_run_findings: null,
  }

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-5 gap-2">
        <StatTile
          className="px-4 py-3 gap-1"
          layout="value-top"
          size="lg"
          label="P0 Open"
          value={s.p0_open}
          valueColor="var(--pnl-down)"
          bg={s.p0_open > 0 ? 'rgba(239,68,68,0.10)' : 'var(--bg-1)'}
          pulseValue={s.p0_open > 0}
        />
        <StatTile
          className="px-4 py-3 gap-1"
          layout="value-top"
          size="lg"
          label="P1 Open"
          value={s.p1_open}
          valueColor="var(--status-warning)"
          bg={s.p1_open > 0 ? 'rgba(245,158,11,0.10)' : 'var(--bg-1)'}
        />
        <StatTile
          className="px-4 py-3 gap-1"
          layout="value-top"
          size="lg"
          label="P2 Open"
          value={s.p2_open}
          valueColor="#eab308"
          bg={s.p2_open > 0 ? 'rgba(234,179,8,0.08)' : 'var(--bg-1)'}
        />
        <StatTile
          className="px-4 py-3 gap-1"
          layout="value-top"
          size="lg"
          label="Opportunities"
          value={s.opportunities_open}
          valueColor="var(--accent-primary)"
        />
        <StatTile
          className="px-4 py-3 gap-1"
          layout="value-top"
          size="lg"
          label="Resolved 7d"
          value={s.resolved_this_week}
          valueColor="var(--pnl-up)"
        />
      </div>

      {s.last_run_at && (
        <p className="text-[10px] text-[var(--text-3)]">
          Last run: {formatAge(s.last_run_at)}
          {s.last_run_findings != null && ` · ${s.last_run_findings} findings`}
          {s.last_run_duration_s != null && ` · ${s.last_run_duration_s.toFixed(1)}s`}
        </p>
      )}
    </div>
  )
}
