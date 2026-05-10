import { useNavigate } from 'react-router-dom'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'

export interface PipelineCounts {
  proposed: number
  backtested: number
  paper: number
  live: number
  retired: number
}

interface StrategyPipelineCountsProps {
  counts: PipelineCounts
  loading?: boolean
  className?: string
}

const ROWS: Array<{
  key: keyof PipelineCounts
  label: string
  color: string
  statusFilter: string
  includeRetired?: boolean
}> = [
  { key: 'proposed', label: 'Proposed', color: 'var(--text-2)', statusFilter: 'PROPOSED' },
  { key: 'backtested', label: 'Backtested', color: 'var(--status-warning)', statusFilter: 'BACKTESTED' },
  { key: 'paper', label: 'Paper', color: 'var(--accent-secondary)', statusFilter: 'PAPER' },
  { key: 'live', label: 'Live', color: 'var(--account-live)', statusFilter: 'LIVE' },
  { key: 'retired', label: 'Retired', color: 'var(--text-3)', statusFilter: 'RETIRED', includeRetired: true },
]

export function StrategyPipelineCounts({ counts, loading, className }: StrategyPipelineCountsProps) {
  const navigate = useNavigate()

  return (
    <div className={cn('p-2', className)}>
      <SectionLabel>Pipeline</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] overflow-hidden bg-[var(--bg-1)]">
        <ul className="divide-y divide-[var(--border-subtle)]">
          {ROWS.map((row) => {
            const value = counts[row.key]
            const handleClick = () => {
              const search = new URLSearchParams({ status: row.statusFilter })
              if (row.includeRetired) search.set('include_retired', 'true')
              navigate(`/strategies/library?${search.toString()}`)
            }
            return (
              <li key={row.key}>
                <button
                  type="button"
                  onClick={handleClick}
                  className="w-full flex items-center px-2 py-1.5 hover:bg-[var(--bg-hover)] transition-colors"
                >
                  <span
                    className="h-1.5 w-1.5 rounded-full shrink-0 mr-2"
                    style={{ backgroundColor: row.color }}
                    aria-hidden
                  />
                  <span className="text-[11px] text-[var(--text-1)] font-medium">{row.label}</span>
                  <span
                    className={cn(
                      'ml-auto mono text-[12px] font-semibold',
                      loading ? 'text-[var(--text-3)]' : 'text-[var(--text-0)]',
                    )}
                  >
                    {loading ? '…' : value.toLocaleString('en-US')}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </div>
    </div>
  )
}
