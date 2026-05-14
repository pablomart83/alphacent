import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { RowSelectionState, SortingState } from '@tanstack/react-table'
import { Inbox } from 'lucide-react'
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
} from '@/components/primitives'
import { classifyError, notifyError } from '@/lib/errors'
import { downloadCsv, type CsvColumn } from '@/lib/csv'
import { useTradingMode } from '@/stores'
import { toast } from 'sonner'
import {
  useClosePositions,
  useCloseAllPositions,
  useOpenPositions,
  useSyncPositions,
  type PositionRow,
} from '../useBookData'
import { ModifyRiskDialog } from '@/components/trading/ModifyRiskDialog'
import { PositionsFilterBar, type PositionFilters } from './PositionsFilterBar'
import { PositionsBulkBar } from './PositionsBulkBar'
import { buildPositionColumns } from './positionColumns'

const DEFAULT_FILTERS: PositionFilters = {
  search: '',
  strategy: '',
  side: 'all',
  status: 'all',
  quickPills: [],
}

export function OpenPositionsTab() {
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)
  const openQuery = useOpenPositions()
  const closeMutation = useClosePositions()
  const closeAllMutation = useCloseAllPositions()
  const syncMutation = useSyncPositions()

  const [filters, setFilters] = useState<PositionFilters>(DEFAULT_FILTERS)
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'pnl', desc: true },
  ])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  const [modifyTarget, setModifyTarget] = useState<PositionRow | null>(null)
  const [closeTarget, setCloseTarget] = useState<PositionRow | null>(null)
  const [confirmCloseSelected, setConfirmCloseSelected] = useState(false)
  const [confirmCloseAll, setConfirmCloseAll] = useState(false)

  const allRows = openQuery.data?.positions ?? []

  const strategyOptions = useMemo(() => {
    const s = new Set<string>()
    for (const r of allRows) {
      if (r.strategy_name) s.add(r.strategy_name)
    }
    return Array.from(s).sort()
  }, [allRows])

  const rows = useMemo(() => {
    const q = filters.search.trim().toLowerCase()
    const now = Date.now()
    return allRows.filter((r) => {
      if (filters.side === 'long') {
        const up = (r.side || '').toUpperCase()
        if (up.includes('SHORT') || up.includes('SELL')) return false
      }
      if (filters.side === 'short') {
        const up = (r.side || '').toUpperCase()
        if (!(up.includes('SHORT') || up.includes('SELL'))) return false
      }
      if (filters.status === 'open' && r.pending_closure) return false
      if (filters.status === 'pending' && !r.pending_closure) return false
      if (filters.strategy && r.strategy_name !== filters.strategy) return false
      if (q) {
        const hit =
          r.symbol.toLowerCase().includes(q) ||
          (r.strategy_name || '').toLowerCase().includes(q)
        if (!hit) return false
      }
      // Quick pills — all active pills must match (AND logic)
      for (const pill of filters.quickPills) {
        const openedMs = r.opened_at
          ? new Date(r.opened_at.endsWith('Z') ? r.opened_at : `${r.opened_at}Z`).getTime()
          : 0
        const heldDays = (now - openedMs) / 86_400_000
        if (pill === 'today'         && heldDays > 1) return false
        if (pill === '48h'           && heldDays > 2) return false
        if (pill === 'losing'        && (r.unrealized_pnl ?? 0) >= 0) return false
        if (pill === 'big-loss'      && (r.unrealized_pnl_percent ?? 0) > -5) return false
        if (pill === 'long-held'     && heldDays < 14) return false
        if (pill === 'pending-close' && !r.pending_closure) return false
      }
      return true
    })
  }, [allRows, filters])

  const handleRowMenu = useCallback(
    (action: 'detail' | 'modify-risk' | 'close', row: PositionRow) => {
      if (action === 'detail') navigate(`/book/position/${encodeURIComponent(row.symbol)}`)
      if (action === 'modify-risk') setModifyTarget(row)
      if (action === 'close') setCloseTarget(row)
    },
    [navigate],
  )

  const columns = useMemo(
    () => buildPositionColumns({ onRowMenuAction: handleRowMenu }),
    [handleRowMenu],
  )

  const selectedIds = useMemo(
    () => Object.keys(rowSelection).filter((id) => rowSelection[id]),
    [rowSelection],
  )

  const handleCloseConfirmed = async () => {
    if (!closeTarget) return
    try {
      const res = await closeMutation.mutateAsync({
        positionIds: [closeTarget.id],
        mode,
      })
      toast.success(`Closed ${res.closed_count} position${res.closed_count === 1 ? '' : 's'}`)
    } catch (err) {
      notifyError(err, 'close position')
    } finally {
      setCloseTarget(null)
    }
  }

  const handleCloseSelectedConfirmed = async () => {
    try {
      const res = await closeMutation.mutateAsync({
        positionIds: selectedIds,
        mode,
      })
      toast.success(`Closed ${res.closed_count} of ${selectedIds.length} selected`)
      setRowSelection({})
    } catch (err) {
      notifyError(err, 'close selected')
    } finally {
      setConfirmCloseSelected(false)
    }
  }

  const handleCloseAllConfirmed = async () => {
    try {
      const res = await closeAllMutation.mutateAsync(mode)
      toast.success(res.message || `Closed ${res.closed_count} positions`)
      setRowSelection({})
    } catch (err) {
      notifyError(err, 'close all')
    } finally {
      setConfirmCloseAll(false)
    }
  }

  const handleSync = async () => {
    try {
      const res = await syncMutation.mutateAsync(mode)
      toast.success(`Synced — ${res.synced} positions (${res.added} added, ${res.updated} updated)`)
    } catch (err) {
      notifyError(err, 'sync positions')
    }
  }

  const handleExport = () => {
    const columnsCsv: CsvColumn<PositionRow>[] = [
      { header: 'Symbol', value: (r) => r.symbol },
      { header: 'Strategy', value: (r) => r.strategy_name ?? '' },
      { header: 'Side', value: (r) => r.side },
      { header: 'Status', value: (r) => (r.pending_closure ? 'Pending close' : 'Open') },
      { header: 'Invested', value: (r) => r.invested_amount ?? r.quantity ?? 0 },
      { header: 'Entry', value: (r) => r.entry_price },
      { header: 'Current', value: (r) => r.current_price },
      { header: 'PnL', value: (r) => r.unrealized_pnl },
      { header: 'PnL %', value: (r) => r.unrealized_pnl_percent },
      { header: 'SL', value: (r) => r.stop_loss ?? '' },
      { header: 'TP', value: (r) => r.take_profit ?? '' },
      { header: 'Sector', value: (r) => r.sector ?? '' },
      { header: 'Asset class', value: (r) => r.asset_class ?? '' },
      { header: 'Opened', value: (r) => r.opened_at },
    ]
    const now = new Date().toISOString().replace(/[:.]/g, '-')
    downloadCsv(`alphacent-positions-${mode}-${now}`, rows, columnsCsv)
  }

  if (openQuery.isError) {
    const info = classifyError(openQuery.error, 'open positions')
    return (
      <ErrorState
        title="Couldn't load positions"
        message={info.message}
        onRetry={() => openQuery.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      <PositionsFilterBar
        filters={filters}
        onChange={setFilters}
        strategyOptions={strategyOptions}
        resultCount={rows.length}
        totalCount={allRows.length}
      />
      <PositionsBulkBar
        selectedCount={selectedIds.length}
        totalCount={allRows.length}
        onCloseSelected={() => setConfirmCloseSelected(true)}
        onCloseAll={() => setConfirmCloseAll(true)}
        onSync={handleSync}
        onExportCsv={handleExport}
        isSyncing={syncMutation.isPending}
        isClosing={closeMutation.isPending || closeAllMutation.isPending}
      />
      <div className="flex-1 min-h-0">
        <DataTable<PositionRow>
          data={rows}
          columns={columns}
          rowKey={(r) => r.id}
          loading={openQuery.isLoading}
          sorting={{ state: sorting, onChange: setSorting }}
          selection={{
            mode: 'multi',
            selected: rowSelection,
            onChange: setRowSelection,
          }}
          density="default"
          emptyState={
            <EmptyState
              icon={Inbox}
              title={allRows.length === 0 ? 'No open positions' : 'No matches'}
              description={
                allRows.length === 0
                  ? 'When strategies open positions, they appear here. The account is idle.'
                  : 'Adjust the filters to widen the set.'
              }
            />
          }
        />
      </div>

      {/* Dialogs */}
      <ModifyRiskDialog
        position={modifyTarget}
        open={!!modifyTarget}
        onOpenChange={(o) => !o && setModifyTarget(null)}
      />
      <ConfirmDialog
        open={!!closeTarget}
        onOpenChange={(o) => !o && setCloseTarget(null)}
        title="Close position"
        description={
          closeTarget
            ? `Close ${closeTarget.symbol} (${closeTarget.side})? This submits a market close order via eToro.`
            : ''
        }
        confirmLabel="Close position"
        confirmVariant="destructive"
        isLoading={closeMutation.isPending}
        onConfirm={handleCloseConfirmed}
      />
      <ConfirmDialog
        open={confirmCloseSelected}
        onOpenChange={setConfirmCloseSelected}
        title={`Close ${selectedIds.length} selected positions`}
        description="Each is submitted as a market close order via eToro. Partial failures return errors per position."
        confirmLabel="Close selected"
        confirmVariant="destructive"
        isLoading={closeMutation.isPending}
        onConfirm={handleCloseSelectedConfirmed}
      />
      <ConfirmDialog
        open={confirmCloseAll}
        onOpenChange={setConfirmCloseAll}
        title="Close ALL open positions"
        description={`This closes every open ${mode} position (${allRows.length} total). Hard to reverse. Proceed?`}
        confirmLabel="Close all"
        confirmVariant="destructive"
        isLoading={closeAllMutation.isPending}
        onConfirm={handleCloseAllConfirmed}
      />
    </div>
  )
}
