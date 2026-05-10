import { useMemo } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { AlertCircle, CheckCheck, TrendingDown, X } from 'lucide-react'
import { Button, EmptyState, ErrorState, Skeleton } from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError, notifyError } from '@/lib/errors'
import { cn, formatAge, formatCurrency } from '@/lib/utils'
import { toast } from 'sonner'
import { useTradingMode } from '@/stores'
import { api } from '@/services/api'
import {
  useApproveClosure,
  useDismissFundamentalAlert,
  useFundamentalAlerts,
  type FundamentalAlertRow,
} from '../useBookData'

export function FundamentalAlertsTab() {
  const mode = useTradingMode((s) => s.mode)
  const qc = useQueryClient()
  const query = useFundamentalAlerts()
  const approve = useApproveClosure()
  const dismiss = useDismissFundamentalAlert()
  const rows = query.data?.alerts ?? []

  const handleTriggerCheck = async () => {
    try {
      const res = await api.post<{
        success: boolean
        flagged: number
        message?: string
      }>('/account/positions/trigger-fundamental-check', undefined, { mode })
      toast.success(`Fundamental scan complete — ${res.flagged ?? 0} positions flagged`)
      qc.invalidateQueries({ queryKey: ['fundamental-alerts', mode] })
    } catch (e) {
      notifyError(e, 'trigger fundamental check')
    }
  }

  const handleClose = async (row: FundamentalAlertRow) => {
    try {
      await approve.mutateAsync({ positionId: row.id, mode })
      toast.success(`Closed ${row.symbol} on fundamental signal`)
    } catch (e) {
      notifyError(e, 'approve closure')
    }
  }

  const handleDismiss = async (row: FundamentalAlertRow) => {
    try {
      await dismiss.mutateAsync({ positionId: row.id, mode })
      toast.success(`Dismissed alert — keeping ${row.symbol}`)
    } catch (e) {
      notifyError(e, 'dismiss alert')
    }
  }

  const content = useMemo(() => {
    if (query.isError) {
      const info = classifyError(query.error, 'fundamental alerts')
      return (
        <ErrorState
          title="Couldn't load fundamental alerts"
          message={info.message}
          onRetry={() => query.refetch()}
        />
      )
    }
    if (query.isLoading && rows.length === 0) {
      return (
        <div className="flex flex-col gap-2 p-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <Skeleton key={i} variant="block" className="h-24" />
          ))}
        </div>
      )
    }
    if (rows.length === 0) {
      return (
        <EmptyState
          icon={TrendingDown}
          title="No fundamental alerts"
          description="When earnings miss, revenue decline, or sector rotation flags a position, it surfaces here with the specific fundamental reason."
          className="py-10"
        />
      )
    }
    return (
      <ul className="flex flex-col gap-2 p-3">
        {rows.map((row) => (
          <AlertCard
            key={row.id}
            row={row}
            onClose={() => handleClose(row)}
            onDismiss={() => handleDismiss(row)}
            closing={approve.isPending && approve.variables?.positionId === row.id}
            dismissing={dismiss.isPending && dismiss.variables?.positionId === row.id}
          />
        ))}
      </ul>
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.isLoading, query.isError, rows, approve.isPending, dismiss.isPending])

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
        <span className="text-[11px] text-[var(--text-2)]">
          {rows.length} alert{rows.length === 1 ? '' : 's'}
        </span>
        <div className="ml-auto">
          <Button variant="secondary" size="sm" onClick={handleTriggerCheck} className="gap-1">
            <CheckCheck className="h-3 w-3" />
            Run fundamental scan
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0 overflow-auto">{content}</div>
    </div>
  )
}

function AlertCard({
  row,
  onClose,
  onDismiss,
  closing,
  dismissing,
}: {
  row: FundamentalAlertRow
  onClose: () => void
  onDismiss: () => void
  closing?: boolean
  dismissing?: boolean
}) {
  const side = (row.side || 'LONG').toUpperCase()
  return (
    <li
      className={cn(
        'rounded-[4px] border bg-[var(--bg-1)] p-3',
        'border-[var(--status-error)]/35',
      )}
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="h-4 w-4 mt-[2px] text-[var(--status-error)] shrink-0" />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="mono font-semibold text-[13px] text-[var(--text-0)]">{row.symbol}</span>
            <span className="text-[10px] uppercase text-[var(--text-3)]">{side}</span>
            <span className="ml-auto text-[10px] text-[var(--text-3)]">
              flagged {formatAge(row.flag_timestamp || row.opened_at)}
            </span>
          </div>
          <div className="mt-1 flex items-baseline gap-3 text-[11px]">
            <span className="text-[var(--text-2)]">{row.strategy_name || 'Strategy'}</span>
            <span className="mono tabular-nums text-[var(--text-2)]">
              invested {formatCurrency(row.invested_amount ?? row.quantity ?? 0, { precision: 0 })}
            </span>
            <PnLNumber
              value={row.unrealized_pnl}
              format="currency"
              precision={0}
              size="sm"
            />
            <PnLNumber
              value={row.unrealized_pnl_percent}
              format="percentage"
              precision={2}
              size="sm"
            />
          </div>
          {row.flag_reason && (
            <p className="mt-2 text-[11px] leading-[16px] text-[var(--text-0)] font-medium">
              {row.flag_reason}
            </p>
          )}
          {row.closure_reason && row.closure_reason !== row.flag_reason && (
            <p className="mt-1 text-[10px] leading-[14px] text-[var(--text-2)]">
              {row.closure_reason}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <Button variant="destructive" size="sm" onClick={onClose} loading={closing}>
            Close position
          </Button>
          <Button variant="ghost" size="sm" onClick={onDismiss} loading={dismissing} className="gap-1">
            <X className="h-3 w-3" />
            Dismiss alert
          </Button>
        </div>
      </div>
    </li>
  )
}
