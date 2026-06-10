import { useState } from 'react'
import { Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'
import { FindingsList } from './FindingsList'
import { FindingDetail } from './FindingDetail'
import { IntelOverview } from './IntelOverview'
import { RunHistoryPanel } from './RunHistoryPanel'
import {
  useIntelFindings,
  useIntelFinding,
  useIntelRuns,
  useIntelSummary,
  useRunAnalysis,
  severityColor,
  formatAge,
  type IntelFindingsFilters,
} from './useIntelData'

const LOOKBACK_OPTIONS = [
  { value: 1, label: '1 day' },
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
]

const SEV_PILLS = [
  { sev: 'P0', label: 'P0' },
  { sev: 'P1', label: 'P1' },
  { sev: 'P2', label: 'P2' },
  { sev: 'opportunity', label: 'Opp' },
]

export function IntelPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [lookback, setLookback] = useState(7)
  const [showLookbackPicker, setShowLookbackPicker] = useState(false)
  const [showHistory, setShowHistory] = useState(false)
  const [filters, setFilters] = useState<IntelFindingsFilters & { statusTab: string }>({
    statusTab: 'open',
    status: 'open',
    category: undefined,
    severity: undefined,
  })

  const summary = useIntelSummary()
  const findings = useIntelFindings({
    status: filters.statusTab === 'all' ? undefined : filters.statusTab,
    category: filters.category,
    severity: filters.severity,
  })
  const selectedFinding = useIntelFinding(selectedId)
  const runs = useIntelRuns()
  const runAnalysis = useRunAnalysis()

  const allFindings = findings.data ?? []

  const handleFiltersChange = (
    patch: Partial<IntelFindingsFilters & { statusTab: string }>,
  ) => {
    setFilters((prev) => {
      const next = { ...prev, ...patch }
      if (patch.statusTab !== undefined) {
        next.status = patch.statusTab === 'all' ? undefined : patch.statusTab
      }
      return next
    })
    setSelectedId(null)
  }

  const handleRun = () => {
    setShowLookbackPicker(false)
    runAnalysis.mutate(lookback)
  }

  const s = summary.data

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">

      {/* ── Top bar ─────────────────────────────────────────────────── */}
      <div className="shrink-0 px-4 py-2.5 border-b border-[var(--border-subtle)] flex items-center gap-3">

        {/* Severity pills */}
        <div className="flex items-center gap-1.5">
          {SEV_PILLS.map(({ sev, label }) => {
            const count =
              sev === 'P0' ? (s?.p0_open ?? 0)
              : sev === 'P1' ? (s?.p1_open ?? 0)
              : sev === 'P2' ? (s?.p2_open ?? 0)
              : (s?.opportunities_open ?? 0)
            const active = filters.severity === sev
            return (
              <button
                key={sev}
                type="button"
                onClick={() =>
                  handleFiltersChange({ severity: active ? undefined : sev })
                }
                className={cn(
                  'flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-semibold mono transition-all border',
                  active
                    ? 'border-transparent'
                    : 'border-[var(--border-subtle)] text-[var(--text-3)] hover:text-[var(--text-1)]',
                )}
                style={
                  active
                    ? {
                        background: `${severityColor(sev)}20`,
                        color: severityColor(sev),
                        borderColor: `${severityColor(sev)}40`,
                      }
                    : undefined
                }
              >
                <span
                  className="w-1.5 h-1.5 rounded-full"
                  style={{ background: count > 0 ? severityColor(sev) : 'var(--text-3)' }}
                />
                {label}
                <span
                  className={cn(
                    'tabular-nums',
                    count > 0 ? '' : 'text-[var(--text-3)]',
                  )}
                  style={count > 0 && !active ? { color: severityColor(sev) } : undefined}
                >
                  {count}
                </span>
              </button>
            )
          })}

          {/* Resolved */}
          <span className="text-[10px] text-[var(--text-3)] ml-1">
            ✓ {s?.resolved_this_week ?? 0} resolved 7d
          </span>
        </div>

        {/* Spacer */}
        <div className="flex-1" />

        {/* Last run info */}
        {s?.last_run_at && (
          <button
            type="button"
            onClick={() => setShowHistory((v) => !v)}
            className="text-[10px] text-[var(--text-3)] hover:text-[var(--text-1)] transition-colors"
          >
            Last run {formatAge(s.last_run_at)}
            {s.last_run_findings != null && ` · ${s.last_run_findings} findings`}
            {s.last_run_duration_s != null && ` · ${s.last_run_duration_s.toFixed(1)}s`}
          </button>
        )}

        {/* Run button */}
        <div className="relative">
          <Button
            variant="primary"
            size="sm"
            onClick={() => setShowLookbackPicker((v) => !v)}
            disabled={runAnalysis.isPending}
            className="gap-1.5 h-7 text-[11px]"
          >
            {runAnalysis.isPending ? (
              <RefreshCw className="h-3 w-3 animate-spin" />
            ) : (
              <Play className="h-3 w-3" />
            )}
            {runAnalysis.isPending ? 'Running…' : 'Run Analysis'}
          </Button>

          {showLookbackPicker && (
            <div className="absolute right-0 top-full mt-1 z-50 bg-[var(--bg-2)] border border-[var(--border-default)] rounded shadow-lg p-3 w-40">
              <p className="text-[9px] font-semibold text-[var(--text-3)] mb-2 uppercase tracking-wide">
                Lookback window
              </p>
              <div className="space-y-1">
                {LOOKBACK_OPTIONS.map((opt) => (
                  <label key={opt.value} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="lookback"
                      value={opt.value}
                      checked={lookback === opt.value}
                      onChange={() => setLookback(opt.value)}
                      className="accent-[var(--accent-primary)]"
                    />
                    <span
                      className={cn(
                        'text-[11px]',
                        lookback === opt.value ? 'text-[var(--text-0)]' : 'text-[var(--text-2)]',
                      )}
                    >
                      {opt.label}
                    </span>
                  </label>
                ))}
              </div>
              <div className="flex gap-1.5 mt-3">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setShowLookbackPicker(false)}
                  className="flex-1 text-[var(--text-2)] h-6 text-[10px]"
                >
                  Cancel
                </Button>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={handleRun}
                  className="flex-1 h-6 text-[10px]"
                >
                  Run →
                </Button>
              </div>
            </div>
          )}
        </div>

        {runAnalysis.isSuccess && runAnalysis.data && (
          <span className="text-[10px] text-[var(--pnl-up)]">
            ✓ {runAnalysis.data.findings_count} in {(runAnalysis.data.duration_s ?? 0).toFixed(1)}s
          </span>
        )}
        {runAnalysis.isError && (
          <span className="text-[10px] text-[var(--pnl-down)]">Run failed</span>
        )}
      </div>

      {/* Run history (collapsible) */}
      {showHistory && (
        <div className="shrink-0 px-4 py-2 border-b border-[var(--border-subtle)]">
          <RunHistoryPanel runs={runs.data ?? []} loading={runs.isLoading} />
        </div>
      )}

      {/* ── Main split ──────────────────────────────────────────────── */}
      <div className="flex flex-1 min-h-0">

        {/* Left: findings list */}
        <div className="w-64 shrink-0 border-r border-[var(--border-subtle)] flex flex-col min-h-0">
          <FindingsList
            findings={allFindings}
            loading={findings.isLoading}
            selectedId={selectedId}
            onSelect={setSelectedId}
            filters={filters}
            onFiltersChange={handleFiltersChange}
          />
        </div>

        {/* Right: detail or overview */}
        <div className="flex-1 min-w-0 min-h-0">
          {selectedId ? (
            <FindingDetail
              finding={selectedFinding.data}
              loading={selectedFinding.isLoading && !!selectedId}
            />
          ) : (
            <IntelOverview
              findings={allFindings}
              onSelect={setSelectedId}
            />
          )}
        </div>
      </div>
    </div>
  )
}
