import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { RowSelectionState, SortingState } from '@tanstack/react-table'
import { Download, Plus, RefreshCw, Trash2 } from 'lucide-react'
import {
  Button,
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
} from '@/components/primitives'
import { classifyError, notifyError } from '@/lib/errors'
import { downloadCsv, type CsvColumn } from '@/lib/csv'
import { cn, parseUtcIso } from '@/lib/utils'
import { toast } from 'sonner'
import { Inbox } from 'lucide-react'
import { useTradingMode } from '@/stores'
import {
  useBulkDeleteOrders,
  useCancelOrder,
  useClosePositionFromOrder,
  useDeleteOrder,
  useOrders,
  useSyncOrders,
  type OrderRow,
} from '../useBookData'
import { OrdersFilterBar, type OrderFilters } from './OrdersFilterBar'
import { buildOrderColumns, slippageBps } from './orderColumns'
import { PlaceOrderDialog } from './PlaceOrderDialog'
import { OrderDetailDialog } from './OrderDetailDialog'

const DEFAULT_FILTERS: OrderFilters = {
  search: '',
  strategy: '',
  side: 'all',
  status: 'all',
  action: 'all',
  range: '30d',
  quickPills: [],
}

/** Kept in sync with the Closed-positions tab. */
const RANGE_DAYS: Record<OrderFilters['range'], number | null> = {
  '1d': 1,
  '7d': 7,
  '30d': 30,
  all: null,
}

interface AllOrdersTabProps {
  /** When set, initial status filter + lock the status select. */
  initialStatus?: OrderFilters['status']
  lockStatus?: boolean
  /** Client-side predicate applied before filters — use for multi-status tabs. */
  clientFilter?: (row: OrderRow) => boolean
  /** Render a small banner explaining a scoped view. */
  banner?: React.ReactNode
  /** ID to make the footnote identify the tab (rare). */
  dataTestId?: string
  /** Pin the data source to a specific account — overrides the global toggle. */
  pinMode?: 'DEMO' | 'LIVE'
}

export function AllOrdersTab({
  initialStatus,
  lockStatus,
  clientFilter,
  banner,
  pinMode,
}: AllOrdersTabProps = {}) {
  const navigate = useNavigate()
  const activeMode = useTradingMode((s) => s.mode)
  const mode = pinMode ?? activeMode

  const [filters, setFilters] = useState<OrderFilters>({
    ...DEFAULT_FILTERS,
    status: initialStatus ?? DEFAULT_FILTERS.status,
  })
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'created', desc: true },
  ])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  const [detailOrder, setDetailOrder] = useState<OrderRow | null>(null)
  const [cancelTarget, setCancelTarget] = useState<OrderRow | null>(null)
  const [deleteTarget, setDeleteTarget] = useState<OrderRow | null>(null)
  const [closePositionTarget, setClosePositionTarget] = useState<OrderRow | null>(null)
  const [confirmBulkDelete, setConfirmBulkDelete] = useState(false)
  const [showPlaceDialog, setShowPlaceDialog] = useState(false)

  const ordersQuery = useOrders({ limit: 2000, pinMode })
  const cancelMutation = useCancelOrder()
  const deleteMutation = useDeleteOrder()
  const bulkDeleteMutation = useBulkDeleteOrders()
  const closePositionMutation = useClosePositionFromOrder()
  const syncMutation = useSyncOrders()

  const allRows = ordersQuery.data?.orders ?? []

  const strategyOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of allRows) if (r.strategy_name) s.add(r.strategy_name)
    return [...s].sort()
  }, [allRows])

  const rows = useMemo(() => {
    const q = filters.search.trim().toLowerCase()
    const days = RANGE_DAYS[filters.range]
    const cutoff = days != null ? Date.now() - days * 86_400_000 : 0

    return allRows.filter((r) => {
      if (clientFilter && !clientFilter(r)) return false
      if (filters.side !== 'all' && r.side !== filters.side) return false
      if (filters.status !== 'all' && r.status !== filters.status) return false
      if (filters.action !== 'all' && r.order_action !== filters.action) return false
      if (filters.strategy && r.strategy_name !== filters.strategy) return false
      if (days != null) {
        const ref = r.created_at ? parseUtcIso(r.created_at).getTime() : 0
        if (!Number.isNaN(ref) && ref < cutoff) return false
      }
      if (q) {
        const hit =
          r.symbol.toLowerCase().includes(q) ||
          (r.strategy_name || '').toLowerCase().includes(q) ||
          r.id.toLowerCase().includes(q)
        if (!hit) return false
      }
      // Quick pills — all active pills must match (AND logic)
      for (const pill of filters.quickPills) {
        const createdMs = r.created_at ? parseUtcIso(r.created_at).getTime() : 0
        const ageHours = (Date.now() - createdMs) / 3_600_000
        if (pill === 'today'  && ageHours > 24) return false
        if (pill === '48h'    && ageHours > 48) return false
        if (pill === 'filled' && r.status !== 'FILLED') return false
        if (pill === 'failed' && !['FAILED','REJECTED','CANCELLED'].includes(r.status)) return false
        if (pill === 'entry'  && r.order_action !== 'entry') return false
        if (pill === 'close'  && r.order_action !== 'close') return false
      }
      return true
    })
  }, [allRows, filters, clientFilter])

  const handleCancel = useCallback(
    async (row: OrderRow) => {
      try {
        const res = await cancelMutation.mutateAsync({ orderId: row.id, mode })
        toast.success(res.message || `Cancelled order ${row.id.slice(0, 8)}`)
      } catch (e) {
        notifyError(e, 'cancel order')
      } finally {
        setCancelTarget(null)
      }
    },
    [cancelMutation, mode],
  )

  const handleDelete = useCallback(
    async (row: OrderRow) => {
      try {
        const res = await deleteMutation.mutateAsync({ orderId: row.id, mode })
        toast.success(res.message || 'Order deleted')
      } catch (e) {
        notifyError(e, 'delete order')
      } finally {
        setDeleteTarget(null)
      }
    },
    [deleteMutation, mode],
  )

  const handleClosePosition = useCallback(
    async (row: OrderRow) => {
      try {
        const res = await closePositionMutation.mutateAsync({ orderId: row.id, mode })
        toast.success(res.message || 'Closing resulting position')
      } catch (e) {
        notifyError(e, 'close position from order')
      } finally {
        setClosePositionTarget(null)
      }
    },
    [closePositionMutation, mode],
  )

  const handleRowAction = useCallback(
    (action: 'cancel' | 'delete' | 'close-position' | 'view', row: OrderRow) => {
      if (action === 'view') setDetailOrder(row)
      if (action === 'cancel') setCancelTarget(row)
      if (action === 'delete') setDeleteTarget(row)
      if (action === 'close-position') setClosePositionTarget(row)
    },
    [],
  )

  const columns = useMemo(
    () =>
      buildOrderColumns({
        onCancel: (r) => handleRowAction('cancel', r),
        onDelete: (r) => handleRowAction('delete', r),
        onClosePosition: (r) => handleRowAction('close-position', r),
        onViewOrder: (r) => handleRowAction('view', r),
      }),
    [handleRowAction],
  )

  const selectedIds = useMemo(
    () => Object.keys(rowSelection).filter((id) => rowSelection[id]),
    [rowSelection],
  )

  const handleBulkDelete = async () => {
    if (selectedIds.length === 0) return
    try {
      const res = await bulkDeleteMutation.mutateAsync({ orderIds: selectedIds, mode })
      toast.success(`Deleted ${res.success_count} of ${selectedIds.length} orders`)
      setRowSelection({})
    } catch (e) {
      notifyError(e, 'bulk delete')
    } finally {
      setConfirmBulkDelete(false)
    }
  }

  const handleSync = async () => {
    try {
      const res = await syncMutation.mutateAsync(mode)
      toast.success(`Synced — ${res.synced} orders (${res.added} added, ${res.updated} updated)`)
    } catch (e) {
      notifyError(e, 'sync orders')
    }
  }

  const handleExport = () => {
    const cols: CsvColumn<OrderRow>[] = [
      { header: 'Order ID', value: (r) => r.id },
      { header: 'Symbol', value: (r) => r.symbol },
      { header: 'Strategy', value: (r) => r.strategy_name ?? '' },
      { header: 'Side', value: (r) => r.side },
      { header: 'Action', value: (r) => r.order_action ?? '' },
      { header: 'Type', value: (r) => r.order_type },
      { header: 'Quantity', value: (r) => r.quantity },
      { header: 'Expected', value: (r) => r.expected_price ?? '' },
      { header: 'Filled', value: (r) => r.filled_price ?? '' },
      { header: 'Slippage bps', value: (r) => slippageBps(r) ?? '' },
      { header: 'Fill time (s)', value: (r) => r.fill_time_seconds ?? '' },
      { header: 'Status', value: (r) => r.status },
      { header: 'Created', value: (r) => r.created_at ?? '' },
      { header: 'Filled at', value: (r) => r.filled_at ?? '' },
    ]
    const now = new Date().toISOString().replace(/[:.]/g, '-')
    downloadCsv(`alphacent-orders-${mode}-${now}`, rows, cols)
  }

  if (ordersQuery.isError) {
    const info = classifyError(ordersQuery.error, 'orders')
    return (
      <ErrorState
        title="Couldn't load orders"
        message={info.message}
        onRetry={() => ordersQuery.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {banner}
      <OrdersFilterBar
        filters={filters}
        onChange={setFilters}
        strategyOptions={strategyOptions}
        resultCount={rows.length}
        totalCount={allRows.length}
        lockStatus={lockStatus}
      />
      <div
        className={cn(
          'flex items-center gap-2 px-2 py-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]',
          selectedIds.length > 0 &&
            'bg-[color-mix(in_oklab,var(--accent-primary)_8%,var(--bg-1))]',
        )}
      >
        {selectedIds.length > 0 ? (
          <>
            <span className="text-[11px] text-[var(--text-1)] font-medium">
              {selectedIds.length} selected
            </span>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setConfirmBulkDelete(true)}
              loading={bulkDeleteMutation.isPending}
              className="gap-1"
            >
              <Trash2 className="h-3 w-3" />
              Delete {selectedIds.length}
            </Button>
          </>
        ) : (
          <span className="text-[11px] text-[var(--text-3)]">
            {allRows.length.toLocaleString('en-US')} orders
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSync}
            loading={syncMutation.isPending}
            className="gap-1"
            title="Re-sync orders from eToro"
          >
            <RefreshCw className="h-3 w-3" />
            Sync
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleExport}
            className="gap-1"
            title="Export filtered rows as CSV"
          >
            <Download className="h-3 w-3" />
            CSV
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => setShowPlaceDialog(true)}
            className="gap-1"
            title="Manual order"
          >
            <Plus className="h-3 w-3" />
            Manual order
          </Button>
        </div>
      </div>
      <div className="flex-1 min-h-0">
        <DataTable<OrderRow>
          data={rows}
          columns={columns}
          rowKey={(r) => r.id}
          loading={ordersQuery.isLoading}
          sorting={{ state: sorting, onChange: setSorting }}
          selection={{
            mode: 'multi',
            selected: rowSelection,
            onChange: setRowSelection,
          }}
          density="default"
          onRowClick={(r) => setDetailOrder(r)}
          emptyState={
            <EmptyState
              icon={Inbox}
              title={allRows.length === 0 ? 'No orders yet' : 'No matches'}
              description={
                allRows.length === 0
                  ? 'Strategy signals submit orders here as they fire.'
                  : 'Adjust the filters to widen the set.'
              }
              action={
                allRows.length === 0 ? (
                  <Button variant="secondary" size="sm" onClick={() => navigate('/strategies')}>
                    Open Strategies
                  </Button>
                ) : undefined
              }
            />
          }
        />
      </div>

      <OrderDetailDialog
        order={detailOrder}
        open={!!detailOrder}
        onOpenChange={(o) => !o && setDetailOrder(null)}
      />
      <PlaceOrderDialog
        open={showPlaceDialog}
        onOpenChange={setShowPlaceDialog}
      />
      <ConfirmDialog
        open={!!cancelTarget}
        onOpenChange={(o) => !o && setCancelTarget(null)}
        title="Cancel order"
        description={
          cancelTarget
            ? `Cancel ${cancelTarget.symbol} ${cancelTarget.side} ${cancelTarget.order_type}? If the order is already filled this will be rejected.`
            : ''
        }
        confirmLabel="Cancel order"
        confirmVariant="destructive"
        isLoading={cancelMutation.isPending}
        onConfirm={() => {
          if (cancelTarget) void handleCancel(cancelTarget)
        }}
      />
      <ConfirmDialog
        open={!!deleteTarget}
        onOpenChange={(o) => !o && setDeleteTarget(null)}
        title="Delete order record"
        description="Permanently removes the record from the database. Terminal orders only — no effect on live positions."
        confirmLabel="Delete"
        confirmVariant="destructive"
        isLoading={deleteMutation.isPending}
        onConfirm={() => {
          if (deleteTarget) void handleDelete(deleteTarget)
        }}
      />
      <ConfirmDialog
        open={!!closePositionTarget}
        onOpenChange={(o) => !o && setClosePositionTarget(null)}
        title="Close resulting position"
        description={
          closePositionTarget
            ? `Close the position opened by this ${closePositionTarget.symbol} fill?`
            : ''
        }
        confirmLabel="Close position"
        confirmVariant="destructive"
        isLoading={closePositionMutation.isPending}
        onConfirm={() => {
          if (closePositionTarget) void handleClosePosition(closePositionTarget)
        }}
      />
      <ConfirmDialog
        open={confirmBulkDelete}
        onOpenChange={setConfirmBulkDelete}
        title={`Delete ${selectedIds.length} order records`}
        description="Removes the records from the database. Only terminal orders (FILLED, CANCELLED, REJECTED, FAILED) are actually deleted — pending orders remain."
        confirmLabel="Delete"
        confirmVariant="destructive"
        isLoading={bulkDeleteMutation.isPending}
        onConfirm={handleBulkDelete}
      />
    </div>
  )
}
