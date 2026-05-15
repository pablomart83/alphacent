import { cn } from '@/lib/utils'
import type { IntelFinding, IntelFindingsFilters } from './useIntelData'
import { categoryLabel, formatAge, severityColor } from './useIntelData'

interface Props {
  findings: IntelFinding[]
  loading: boolean
  selectedId: string | null
  onSelect: (id: string) => void
  filters: IntelFindingsFilters & { statusTab: string }
  onFiltersChange: (f: Partial<IntelFindingsFilters & { statusTab: string }>) => void
}

const STATUS_TABS = [
  { value: 'open', label: 'Open' },
  { value: 'dismissed', label: 'Dismissed' },
  { value: 'resolved', label: 'Resolved' },
  { value: 'all', label: 'All' },
]

const CATEGORIES = ['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H']
const SEVERITIES = ['P0', 'P1', 'P2', 'opportunity']

function SeverityDot({ severity }: { severity: string }) {
  const color = severityColor(severity)
  return (
    <span
      className="inline-block w-2 h-2 rounded-full shrink-0 mt-0.5"
      style={{ background: color }}
      aria-hidden
    />
  )
}

export function FindingsList({
  findings,
  loading,
  selectedId,
  onSelect,
  filters,
  onFiltersChange,
}: Props) {
  // Defensive: ensure findings is always an array even if API returns unexpected shape
  const safeFindings = Array.isArray(findings) ? findings : []
  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Status tabs */}
      <div className="flex gap-0 border-b border-[var(--border-subtle)] shrink-0 px-2 pt-1">
        {STATUS_TABS.map((t) => (
          <button
            key={t.value}
            type="button"
            onClick={() => onFiltersChange({ statusTab: t.value })}
            className={cn(
              'px-2.5 h-7 text-[11px] font-medium rounded-t transition-colors',
              filters.statusTab === t.value
                ? 'text-[var(--text-0)] border-b-2 border-[var(--accent-primary)]'
                : 'text-[var(--text-3)] hover:text-[var(--text-1)]',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Filter row */}
      <div className="flex gap-1.5 px-2 py-1.5 shrink-0 border-b border-[var(--border-subtle)]">
        <select
          value={filters.category ?? ''}
          onChange={(e) => onFiltersChange({ category: e.target.value || undefined })}
          className="text-[10px] bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded px-1.5 py-0.5 text-[var(--text-2)] focus:outline-none"
          aria-label="Filter by category"
        >
          <option value="">Category</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {c} — {categoryLabel(c)}
            </option>
          ))}
        </select>

        <select
          value={filters.severity ?? ''}
          onChange={(e) => onFiltersChange({ severity: e.target.value || undefined })}
          className="text-[10px] bg-[var(--bg-1)] border border-[var(--border-subtle)] rounded px-1.5 py-0.5 text-[var(--text-2)] focus:outline-none"
          aria-label="Filter by severity"
        >
          <option value="">Severity</option>
          {SEVERITIES.map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>

        {(filters.category || filters.severity) && (
          <button
            type="button"
            onClick={() => onFiltersChange({ category: undefined, severity: undefined })}
            className="text-[10px] text-[var(--text-3)] hover:text-[var(--text-1)] px-1"
          >
            Clear
          </button>
        )}
      </div>

      {/* List */}
      <div className="flex-1 min-h-0 overflow-y-auto">
        {loading && safeFindings.length === 0 && (
          <div className="space-y-1 p-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-10 rounded bg-[var(--bg-1)] animate-pulse" />
            ))}
          </div>
        )}

        {!loading && safeFindings.length === 0 && (
          <div className="flex items-center justify-center h-32 text-[11px] text-[var(--text-3)]">
            No findings
          </div>
        )}

        {safeFindings.map((f) => (
          <button
            key={f.id}
            type="button"
            onClick={() => onSelect(f.id)}
            className={cn(
              'w-full text-left px-3 py-2 border-b border-[var(--border-subtle)]',
              'hover:bg-[var(--bg-hover)] transition-colors',
              selectedId === f.id && 'bg-[var(--bg-active)]',
            )}
          >
            <div className="flex items-start gap-2">
              <SeverityDot severity={f.severity} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 mb-0.5">
                  <span
                    className="text-[9px] font-semibold mono px-1 rounded"
                    style={{
                      color: severityColor(f.severity),
                      background: `${severityColor(f.severity)}20`,
                    }}
                  >
                    {f.severity}
                  </span>
                  <span className="text-[9px] text-[var(--text-3)]">{f.check_id}</span>
                  <span className="text-[9px] text-[var(--text-3)]">·</span>
                  <span className="text-[9px] text-[var(--text-3)]">{categoryLabel(f.category)}</span>
                </div>
                <p className="text-[11px] text-[var(--text-1)] leading-tight truncate">
                  {/* Strip the check_id prefix from title for display */}
                  {f.title.replace(/^[A-H]\d+:\s*/, '')}
                </p>
                <p className="text-[9px] text-[var(--text-3)] mt-0.5">
                  {formatAge(f.last_seen)}
                  {f.occurrence_count > 1 && ` · ${f.occurrence_count}×`}
                </p>
              </div>
            </div>
          </button>
        ))}
      </div>

      <div className="shrink-0 px-3 py-1.5 border-t border-[var(--border-subtle)]">
        <span className="text-[10px] text-[var(--text-3)]">
          {safeFindings.length} finding{safeFindings.length !== 1 ? 's' : ''}
        </span>
      </div>
    </div>
  )
}
