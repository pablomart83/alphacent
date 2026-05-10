import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Activity, ArrowDownCircle, ArrowUpCircle, Archive, CircleOff, Flag } from 'lucide-react'
import { api } from '@/services/api'
import { useTradingMode } from '@/stores'
import { formatAge, cn } from '@/lib/utils'
import { EmptyState, Skeleton } from '@/components/primitives'

interface AlertEntry {
  id: number
  event_type: string
  strategy_name?: string | null
  symbol?: string | null
  detail: string
  timestamp: string
}

interface StrategyAlertsResponse {
  alerts: AlertEntry[]
  total: number
}

function iconForEvent(eventType: string) {
  switch (eventType) {
    case 'activation':
      return { Icon: ArrowUpCircle, color: 'var(--pnl-up)' }
    case 'retirement':
      return { Icon: Archive, color: 'var(--text-3)' }
    case 'pending_closure':
      return { Icon: Flag, color: 'var(--status-warning)' }
    case 'demotion':
      return { Icon: ArrowDownCircle, color: 'var(--pnl-down)' }
    case 'deactivation':
      return { Icon: CircleOff, color: 'var(--text-3)' }
    default:
      return { Icon: Activity, color: 'var(--text-2)' }
  }
}

export function LifecycleFeed() {
  const mode = useTradingMode((s) => s.mode)
  const navigate = useNavigate()

  const { data, isLoading } = useQuery<StrategyAlertsResponse>({
    queryKey: ['dashboard-strategy-alerts', mode],
    queryFn: () =>
      api.get<StrategyAlertsResponse>('/dashboard/strategy-alerts', {
        mode,
        limit: 15,
      }),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const items = data?.alerts ?? []

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex-1 min-h-0 overflow-auto">
        {isLoading && items.length === 0 && (
          <div className="flex flex-col gap-1 p-2">
            {Array.from({ length: 3 }).map((_, i) => (
              <Skeleton key={i} variant="table-row" />
            ))}
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <EmptyState
            icon={Activity}
            title="No recent lifecycle events"
            description="Activations, retirements, and closure flags stream here."
            className="py-6"
          />
        )}
        <ul className="divide-y divide-[var(--border-subtle)]">
          {items.map((item) => {
            const { Icon, color } = iconForEvent(item.event_type)
            return (
              <li key={item.id}>
                <button
                  type="button"
                  onClick={() => navigate('/strategies')}
                  className={cn(
                    'w-full text-left flex items-start gap-2 px-2 py-1.5 hover:bg-[var(--bg-hover)]',
                  )}
                >
                  <Icon className="h-3 w-3 mt-[2px] shrink-0" style={{ color }} />
                  <div className="flex-1 min-w-0">
                    <div className="text-[11px] text-[var(--text-1)] truncate">
                      <span className="font-medium text-[var(--text-0)]">
                        {item.strategy_name || item.symbol || 'Strategy'}
                      </span>
                      <span className="text-[var(--text-3)]"> · {item.event_type}</span>
                    </div>
                    <div className="text-[10px] text-[var(--text-2)] truncate">
                      {item.detail}
                    </div>
                  </div>
                  <span className="text-[10px] text-[var(--text-3)] mono shrink-0 pt-[2px]">
                    {formatAge(item.timestamp)}
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
