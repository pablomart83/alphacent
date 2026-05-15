import { cn } from '@/lib/utils'
import type { IntelSummary } from './useIntelData'
import { formatAge } from './useIntelData'

interface Props {
  summary: IntelSummary | undefined
  loading: boolean
}

interface TileProps {
  label: string
  value: number | string
  color: string
  bg: string
  pulse?: boolean
}

function Tile({ label, value, color, bg, pulse }: TileProps) {
  return (
    <div
      className="flex flex-col gap-1 px-4 py-3 rounded border border-[var(--border-subtle)]"
      style={{ background: bg }}
    >
      <span
        className={cn(
          'text-2xl font-bold mono tabular-nums',
          pulse && typeof value === 'number' && value > 0 && 'animate-pulse',
        )}
        style={{ color }}
      >
        {value}
      </span>
      <span className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">{label}</span>
    </div>
  )
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
        <Tile
          label="P0 Open"
          value={s.p0_open}
          color="var(--pnl-down)"
          bg={s.p0_open > 0 ? 'rgba(239,68,68,0.10)' : 'var(--bg-1)'}
          pulse={s.p0_open > 0}
        />
        <Tile
          label="P1 Open"
          value={s.p1_open}
          color="var(--status-warning)"
          bg={s.p1_open > 0 ? 'rgba(245,158,11,0.10)' : 'var(--bg-1)'}
        />
        <Tile
          label="P2 Open"
          value={s.p2_open}
          color="#eab308"
          bg={s.p2_open > 0 ? 'rgba(234,179,8,0.08)' : 'var(--bg-1)'}
        />
        <Tile
          label="Opportunities"
          value={s.opportunities_open}
          color="var(--accent-primary)"
          bg="var(--bg-1)"
        />
        <Tile
          label="Resolved 7d"
          value={s.resolved_this_week}
          color="var(--pnl-up)"
          bg="var(--bg-1)"
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
