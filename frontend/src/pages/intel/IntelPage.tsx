import { useState } from 'react'
import { Play, RefreshCw } from 'lucide-react'
import { Button } from '@/components/primitives'
import { cn } from '@/lib/utils'
import { IntelSummaryTiles } from './IntelSummaryTiles'
import { FindingsList } from './FindingsList'
import { FindingDetail } from './FindingDetail'
import { RunHistoryPanel } from './RunHistoryPanel'
import {
  useIntelFindings,
  useIntelFinding,
  useIntelRuns,
  useIntelSummary,
  useRunAnalysis,
  type IntelFindingsFilters,
} from './useIntelData'

const LOOKBACK_OPTIONS = [
  { value: 1, label: '1 day' },
  { value: 7, label: '7 days' },
  { value: 14, label: '14 days' },
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
]

export function IntelPage() {
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [lookback, setLookback] = useState(7)
  const [showLookbackPicker, setShowLookbackPicker] = useState(false)
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

  const handleFiltersChange = (
    patch: Partial<IntelFindingsFilters & { statusTab: string }>,
  ) => {
    setFilters((prev) => {
      const next = { ...prev, ...patch }
      // Keep status in sync with statusTab
      if (patch.statusTab !== undefined) {
        next.status = patch.statusTab === 'all' ? undefined : patch.statusTab
      }
      return next
    })
    // Clear selection when filters change
    setSelectedId(null)
  }

  const handleRun = () => {
    setShowLookbackPicker(false)
    runAnalysis.mutate(lookback)
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      {/* Top bar */}
      <div className="shrink-0 px-4 py-3 border-b border-[var(--border-subtle)] flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0 space-y-3">
          <IntelSummaryTiles
            summary={summary.data}
            loading={summary.isLoading}
          />
          <RunHistoryPanel runs={runs.data ?? []} loading={runs.isLoading} />
        </div>

        {/* Run controls */}
        <div className="shrink-0 flex flex-col items-end gap-2">
          <div className="relative">
            <Button
              variant="primary"
              size="sm"
              onClick={() => setShowLookbackPicker((v) => !v)}
              disabled={runAnalysis.isPending}
              className="gap-1.5"
            >
              {runAnalysis.isPending ? (
                <RefreshCw className="h-3.5 w-3.5 animate-spin" />
              ) : (
                <Play className="h-3.5 w-3.5" />
              )}
              {runAnalysis.isPending ? 'Running…' : 'Run Analysis'}
            </Button>

            {showLookbackPicker && (
              <div className="absolute right-0 top-full mt-1 z-50 bg-[var(--bg-2)] border border-[var(--border-default)] rounded shadow-lg p-3 w-44">
                <p className="text-[10px] font-semibold text-[var(--text-2)] mb-2 uppercase tracking-wide">
                  Lookback window
                </p>
                <div className="space-y-1">
                  {LOOKBACK_OPTIONS.map((opt) => (
                    <label
                      key={opt.value}
                      className="flex items-center gap-2 cursor-pointer group"
                    >
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
                          'text-[11px] group-hover:text-[var(--text-0)] transition-colors',
                          lookback === opt.value
                            ? 'text-[var(--text-0)]'
                            : 'text-[var(--text-2)]',
                        )}
                      >
                        {opt.label}
                      </span>
                    </label>
                  ))}
                </div>
                <div className="flex gap-2 mt-3">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => setShowLookbackPicker(false)}
                    className="flex-1 text-[var(--text-2)]"
                  >
                    Cancel
                  </Button>
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={handleRun}
                    className="flex-1"
                  >
                    Run →
                  </Button>
                </div>
              </div>
            )}
          </div>

          {runAnalysis.isSuccess && runAnalysis.data && (
            <p className="text-[10px] text-[var(--pnl-up)]">
              ✓ {runAnalysis.data.findings_count} findings in {runAnalysis.data.duration_s.toFixed(1)}s
            </p>
          )}
          {runAnalysis.isError && (
            <p className="text-[10px] text-[var(--pnl-down)]">Run failed</p>
          )}
        </div>
      </div>

      {/* Main split */}
      <div className="flex flex-1 min-h-0">
        {/* Left: findings list */}
        <div className="w-72 shrink-0 border-r border-[var(--border-subtle)] flex flex-col min-h-0">
          <FindingsList
            findings={findings.data ?? []}
            loading={findings.isLoading}
            selectedId={selectedId}
            onSelect={setSelectedId}
            filters={filters}
            onFiltersChange={handleFiltersChange}
          />
        </div>

        {/* Right: finding detail */}
        <div className="flex-1 min-w-0 min-h-0">
          <FindingDetail
            finding={selectedFinding.data}
            loading={selectedFinding.isLoading && !!selectedId}
          />
        </div>
      </div>
    </div>
  )
}
