import { useMemo, useState } from 'react'
import { CheckCheck, Flag, XCircle } from 'lucide-react'
import { Button, Checkbox, EmptyState, ErrorState, Skeleton } from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { toast } from 'sonner'
import { classifyError, notifyError } from '@/lib/errors'
import { cn, formatAge, formatCurrency } from '@/lib/utils'
import { useTradingMode } from '@/stores'
import {
  useApproveClosure,
  useApproveClosuresBulk,
  useDismissClosure,
  usePendingClosures,
  type PositionRow,
} from '../useBookData'

export function PendingClosuresTab() {
  const mode = useTradingMode((s) => s.mode)
  const query = usePendingClosures()
  const approve = useApproveClosure()
  const bulkApprove = useApproveClosuresBulk()
  const dismiss = useDismissClosure()

  const rows = query.data?.positions ?? []
  const [selected, setSelected] = useState<Set<string>>(new Set())

  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))

  const toggleAll = () => {
    if (allSelected) setSelected(new Set())
    else setSelected(new Set(rows.map((r) => r.id)))
  }

  const toggle = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  const handleApprove = async (row: PositionRow) => {
    try {
      await approve.mutateAsync({ positionId: row.id, mode })
      toast.success(`Approved closure — ${row.symbol}`)
    } catch (e) {
      notifyError(e, 'approve closure')
    }
  }

  const handleApproveSelected = async () => {
    const ids = Array.from(selected)
    if (ids.length === 0) return
    try {
      const res = await bulkApprove.mutateAsync({ positionIds: ids, mode })
      toast.success(`Approved ${res.success_count} closures · ${res.fail_count} failed`)
      setSelected(new Set())
    } catch (e) {
      notifyError(e, 'bulk approve')
    }
  }

  const handleDismiss = async (row: PositionRow) => {
    try {
      await dismiss.mutateAsync({ positionId: row.id, mode })
      toast.success(`Dismissed closure — ${row.symbol} stays open`)
    } catch (e) {
      notifyError(e, 'dismiss closure')
    }
  }

  const selectedCount = selected.size

  const content = useMemo(() => {
    if (query.isError) {
      const info = classifyError(query.error, 'pending closures')
      return (
        <ErrorState
          title="Couldn't load pending closures"
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
          icon={Flag}
          title="No pending closures"
          description="When monitoring flags positions for closure (trailing-stop breach, fundamental exit), they surface here for review."
          className="py-10"
        />
      )
    }
    return (
      <ul className="flex flex-col gap-2 p-3">
        {rows.map((row) => (
          <ClosureCard
            key={row.id}
            row={row}
            checked={selected.has(row.id)}
            onToggle={() => toggle(row.id)}
            onApprove={() => handleApprove(row)}
            onDismiss={() => handleDismiss(row)}
            approving={approve.isPending && approve.variables?.positionId === row.id}
            dismissing={dismiss.isPending && dismiss.variables?.positionId === row.id}
          />
        ))}
      </ul>
    )
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [query.isLoading, query.isError, rows, selected, approve.isPending, dismiss.isPending])

  return (
    <div className="flex flex-col h-full min-h-0">
      {rows.length > 0 && (
        <div className="flex items-center gap-2 px-3 py-1.5 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
          <Checkbox
            aria-label="Select all"
            checked={allSelected}
            onCheckedChange={toggleAll}
          />
          <span className="text-[11px] text-[var(--text-2)]">
            {selectedCount > 0 ? `${selectedCount} selected` : `${rows.length} flagged`}
          </span>
          <div className="ml-auto">
            <Button
              variant="primary"
              size="sm"
              onClick={handleApproveSelected}
              disabled={selectedCount === 0}
              loading={bulkApprove.isPending}
              className="gap-1"
            >
              <CheckCheck className="h-3 w-3" />
              Approve selected
            </Button>
          </div>
        </div>
      )}
      <div className="flex-1 min-h-0 overflow-auto">{content}</div>
    </div>
  )
}

function ClosureCard({
  row,
  checked,
  onToggle,
  onApprove,
  onDismiss,
  approving,
  dismissing,
}: {
  row: PositionRow
  checked: boolean
  onToggle: () => void
  onApprove: () => void
  onDismiss: () => void
  approving?: boolean
  dismissing?: boolean
}) {
  const isLoss = (row.unrealized_pnl ?? 0) < 0
  const side = (row.side || 'LONG').toUpperCase()
  return (
    <li
      className={cn(
        'rounded-[4px] border bg-[var(--bg-1)] p-3',
        'border-[var(--status-warning)]/40',
      )}
    >
      <div className="flex items-start gap-3">
        <Checkbox checked={checked} onCheckedChange={onToggle} className="mt-1" />
        <div className="flex-1 min-w-0">
          <div className="flex items-baseline gap-2">
            <span className="mono font-semibold text-[13px] text-[var(--text-0)]">{row.symbol}</span>
            <span className="text-[10px] uppercase text-[var(--text-3)]">{side}</span>
            <span className="ml-auto text-[10px] text-[var(--text-3)]">
              opened {formatAge(row.opened_at)}
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
          {row.closure_reason && (
            <p className="mt-2 text-[11px] leading-[16px] text-[var(--text-1)]">
              <span className="text-[var(--status-warning)] font-medium">Reason: </span>
              {row.closure_reason}
            </p>
          )}
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          <Button
            variant={isLoss ? 'destructive' : 'primary'}
            size="sm"
            onClick={onApprove}
            loading={approving}
          >
            Approve close
          </Button>
          <Button variant="ghost" size="sm" onClick={onDismiss} loading={dismissing} className="gap-1">
            <XCircle className="h-3 w-3" />
            Dismiss
          </Button>
        </div>
      </div>
    </li>
  )
}
