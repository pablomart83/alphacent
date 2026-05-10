import { useNavigate } from 'react-router-dom'
import { Activity, Clock, Play } from 'lucide-react'
import { SectionLabel } from '@/components/layout'
import { cn, formatAge, formatTimestamp, parseUtcIso } from '@/lib/utils'

export interface AutonomousStatusShape {
  enabled: boolean
  market_regime?: string
  market_confidence?: number
  data_quality?: string
  last_cycle_time?: string | null
  next_scheduled_run?: string | null
  cycle_duration?: number | null
  cycle_stats?: {
    proposals_generated?: number
    backtest_passed?: number
    activated?: number
    strategies_retired?: number
  }
}

interface CycleStatusCardProps {
  status: AutonomousStatusShape | null | undefined
  className?: string
}

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds || seconds <= 0) return '—'
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  if (m === 0) return `${s}s`
  if (s === 0) return `${m}m`
  return `${m}m ${s}s`
}

export function CycleStatusCard({ status, className }: CycleStatusCardProps) {
  const navigate = useNavigate()

  const nextRunDate = status?.next_scheduled_run ? parseUtcIso(status.next_scheduled_run) : null
  const isNextRunValid = nextRunDate && !Number.isNaN(nextRunDate.getTime())

  const nextRunDelta = isNextRunValid
    ? Math.round((nextRunDate.getTime() - Date.now()) / 1000)
    : null

  const nextRunLabel =
    nextRunDelta == null
      ? '—'
      : nextRunDelta <= 0
        ? 'Running…'
        : nextRunDelta < 60
          ? `in ${nextRunDelta}s`
          : nextRunDelta < 3600
            ? `in ${Math.round(nextRunDelta / 60)}m`
            : `in ${(nextRunDelta / 3600).toFixed(1)}h`

  const stats = status?.cycle_stats ?? {}

  return (
    <div className={cn('p-2 border-b border-[var(--border-subtle)]', className)}>
      <SectionLabel>Cycle</SectionLabel>
      <button
        type="button"
        onClick={() => navigate('/strategies?tab=cycle')}
        className="w-full text-left rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 hover:bg-[var(--bg-hover)] transition-colors"
      >
        <div className="flex items-center justify-between mb-1.5">
          <div className="flex items-center gap-1.5">
            {status?.enabled ? (
              <>
                <Activity className="h-3 w-3 text-[var(--pnl-up)]" />
                <span className="text-[11px] font-medium text-[var(--text-0)]">Autonomous ON</span>
              </>
            ) : (
              <>
                <Activity className="h-3 w-3 text-[var(--text-3)]" />
                <span className="text-[11px] font-medium text-[var(--text-3)]">Autonomous OFF</span>
              </>
            )}
          </div>
          <span className="text-[10px] text-[var(--text-3)] mono">
            {status?.last_cycle_time ? formatAge(status.last_cycle_time) : '—'}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
          <div className="flex items-center gap-1">
            <Clock className="h-2.5 w-2.5 text-[var(--text-3)]" />
            <span className="text-[var(--text-2)]">Next</span>
            <span className="mono text-[var(--text-1)] ml-auto" title={isNextRunValid ? formatTimestamp(nextRunDate!, 'short') : ''}>
              {nextRunLabel}
            </span>
          </div>
          <div className="flex items-center gap-1">
            <Play className="h-2.5 w-2.5 text-[var(--text-3)]" />
            <span className="text-[var(--text-2)]">Last</span>
            <span className="mono text-[var(--text-1)] ml-auto">
              {formatDuration(status?.cycle_duration)}
            </span>
          </div>
          <StatCell label="Proposed" value={stats.proposals_generated} />
          <StatCell label="Backtested" value={stats.backtest_passed} />
          <StatCell label="Activated" value={stats.activated} />
          <StatCell label="Retired" value={stats.strategies_retired} />
        </div>
      </button>
    </div>
  )
}

function StatCell({ label, value }: { label: string; value: number | undefined }) {
  return (
    <div className="flex items-center gap-1">
      <span className="text-[var(--text-2)]">{label}</span>
      <span className="mono text-[var(--text-1)] ml-auto">{value ?? 0}</span>
    </div>
  )
}
