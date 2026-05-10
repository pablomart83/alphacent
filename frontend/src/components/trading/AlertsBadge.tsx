import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Bell } from 'lucide-react'
import { api } from '@/services/api'
import { cn } from '@/lib/utils'

interface AlertHistoryResponse {
  alerts: unknown[]
  unread_count: number
  total: number
}

export function AlertsBadge({ className }: { className?: string }) {
  const navigate = useNavigate()

  const { data } = useQuery<AlertHistoryResponse>({
    queryKey: ['alerts-history', { unread_only: true }],
    queryFn: () =>
      api.get<AlertHistoryResponse>('/alerts/history', {
        limit: 1,
        unread_only: true,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const count = data?.unread_count ?? 0
  const destructive = count > 0

  return (
    <button
      type="button"
      onClick={() => navigate('/guard')}
      className={cn(
        'inline-flex items-center gap-2 rounded-[3px] border px-2 h-7 transition-colors',
        destructive
          ? 'bg-[var(--status-error-bg)] border-[color-mix(in_oklab,var(--status-error)_40%,transparent)] text-[var(--status-error)] hover:brightness-110'
          : 'bg-[var(--bg-1)] border-[var(--border-subtle)] text-[var(--text-2)] hover:bg-[var(--bg-hover)]',
        className,
      )}
      aria-label={`${count} unread alert${count === 1 ? '' : 's'}`}
    >
      <Bell className="h-3 w-3" />
      <span className="text-[11px] font-medium">
        {count === 0 ? 'No alerts' : `${count} unread`}
      </span>
    </button>
  )
}
