import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { IntelRun } from './useIntelData'
import { formatAge } from './useIntelData'

interface Props {
  runs: IntelRun[]
  loading: boolean
}

export function RunHistoryPanel({ runs, loading }: Props) {
  const [open, setOpen] = useState(false)

  return (
    <div className="border border-[var(--border-subtle)] rounded">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2 text-[11px] text-[var(--text-2)] hover:text-[var(--text-0)] transition-colors"
      >
        {open ? (
          <ChevronDown className="h-3 w-3 shrink-0" />
        ) : (
          <ChevronRight className="h-3 w-3 shrink-0" />
        )}
        <span className="font-medium">Run history</span>
        {runs.length > 0 && (
          <span className="text-[var(--text-3)] ml-auto">{runs.length} runs</span>
        )}
      </button>

      {open && (
        <div className="border-t border-[var(--border-subtle)]">
          {loading && runs.length === 0 && (
            <div className="px-3 py-2 text-[10px] text-[var(--text-3)]">Loading…</div>
          )}
          {!loading && runs.length === 0 && (
            <div className="px-3 py-2 text-[10px] text-[var(--text-3)]">No runs yet</div>
          )}
          {runs.map((run) => (
            <div
              key={run.id}
              className="flex items-center gap-3 px-3 py-1.5 border-b border-[var(--border-subtle)] last:border-0"
            >
              <span
                className={cn(
                  'text-[9px] font-medium px-1 rounded',
                  run.status === 'complete'
                    ? 'bg-[rgba(34,197,94,0.15)] text-[var(--pnl-up)]'
                    : run.status === 'error'
                      ? 'bg-[rgba(239,68,68,0.12)] text-[var(--pnl-down)]'
                      : 'bg-[var(--bg-2)] text-[var(--text-3)]',
                )}
              >
                {run.status}
              </span>
              <span className="text-[10px] text-[var(--text-2)]">
                {formatAge(run.started_at)}
              </span>
              <span className="text-[10px] text-[var(--text-3)]">
                {run.lookback_days}d lookback
              </span>
              {run.findings_total != null && (
                <span className="text-[10px] text-[var(--text-3)]">
                  {run.findings_total} findings
                </span>
              )}
              {run.duration_s != null && (
                <span className="text-[10px] text-[var(--text-3)] ml-auto">
                  {run.duration_s.toFixed(1)}s
                </span>
              )}
              {run.error && (
                <span className="text-[10px] text-[var(--pnl-down)] truncate max-w-[200px]" title={run.error}>
                  {run.error}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
