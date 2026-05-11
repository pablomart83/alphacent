import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import type { RowSelectionState, SortingState } from '@tanstack/react-table'
import { Library } from 'lucide-react'
import {
  ConfirmDialog,
  DataTable,
  EmptyState,
  ErrorState,
} from '@/components/primitives'
import { ResizablePanelLayout } from '@/components/layout'
import { downloadCsv } from '@/lib/csv'
import { classifyError, notifyError } from '@/lib/errors'
import { useTradingMode } from '@/stores'
import {
  hasNegativeLivePnl,
  hasPaper20Plus,
  hasSignalToday,
  isGraduationEligible,
  isIdle7d,
  useActivateStrategy,
  useDeactivateStrategy,
  useDeleteStrategyPermanent,
  useRetireStrategy,
  useStrategies,
  useStrategyBacktest,
  type StrategyRow,
  type StrategyStatus,
} from '../useStrategiesData'
import {
  buildStrategyColumns,
  strategyCsvColumns,
} from './strategyColumns'
import {
  LibraryFilterBar,
  type LibraryFilters,
  type QuickPillId,
} from './LibraryFilterBar'
import { LibraryBulkBar } from './LibraryBulkBar'
import { LibraryStatusBar } from './LibraryStatusBar'
import {
  StrategyDetailPanel,
  nextSubTab,
  type DetailSubTab,
} from './StrategyDetailPanel'
import { CompareDialog } from './CompareDialog'
import { usePipelineCounts } from '@/pages/command/useCommandData'

/* ─────────────────────────── URL + filter state ─────────────────────────── */

function serializePills(pills: QuickPillId[]): string | null {
  if (pills.length === 0) return null
  return pills.join(',')
}

function parsePills(raw: string | null): QuickPillId[] {
  if (!raw) return []
  const allowed: QuickPillId[] = [
    'signals-today',
    'idle-7d',
    'negative-live-pnl',
    'graduation-eligible',
    'paper-20-plus',
  ]
  return raw
    .split(',')
    .map((p) => p.trim() as QuickPillId)
    .filter((p) => allowed.includes(p))
}

function filtersFromUrl(params: URLSearchParams): LibraryFilters {
  return {
    search: params.get('search') ?? '',
    status: (params.get('status') as StrategyStatus | 'all') || 'all',
    template: params.get('template') ?? '',
    regime: params.get('regime') ?? '',
    source:
      (params.get('source') as LibraryFilters['source']) &&
      ['all', 'TEMPLATE', 'USER'].includes(params.get('source') || '')
        ? (params.get('source') as LibraryFilters['source'])
        : 'all',
    category: params.get('category') ?? '',
    type: params.get('type') ?? '',
    quickPills: parsePills(params.get('pills')),
  }
}

function syncFiltersToUrl(
  filters: LibraryFilters,
  params: URLSearchParams,
): URLSearchParams {
  const next = new URLSearchParams(params)
  const set = (k: string, v: string | null) => {
    if (!v) next.delete(k)
    else next.set(k, v)
  }
  set('search', filters.search || null)
  set('status', filters.status === 'all' ? null : filters.status)
  set('template', filters.template || null)
  set('regime', filters.regime || null)
  set('source', filters.source === 'all' ? null : filters.source)
  set('category', filters.category || null)
  set('type', filters.type || null)
  set('pills', serializePills(filters.quickPills))
  return next
}

/* ─────────────────────────── Library tab ─────────────────────────── */

export function LibraryTab() {
  const mode = useTradingMode((s) => s.mode)
  const [params, setParams] = useSearchParams()
  const pipelineQuery = usePipelineCounts()

  const [filters, setFilters] = useState<LibraryFilters>(() => filtersFromUrl(params))
  const [sorting, setSorting] = useState<SortingState>([{ id: 'conviction', desc: true }])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})

  const [selectedId, setSelectedId] = useState<string | null>(
    () => params.get('selected'),
  )
  const [detailSub, setDetailSub] = useState<DetailSubTab>('evidence')

  const [confirmAction, setConfirmAction] = useState<
    | {
        kind: 'activate' | 'deactivate' | 'retire' | 'delete-permanent' | 'backtest'
        target: StrategyRow
      }
    | null
  >(null)
  const [confirmBulk, setConfirmBulk] = useState<'activate' | 'retire' | null>(null)
  const [compareOpen, setCompareOpen] = useState(false)

  const tableBodyRef = useRef<HTMLDivElement>(null)

  /* ─── Data ─── */
  const strategiesQuery = useStrategies({ slim: true, include_retired: true })
  const allRows: StrategyRow[] = strategiesQuery.data?.strategies ?? []

  // Count live-authorized strategies from the actual row data (not pipeline counts
  // which use strategies.status — that's never set to LIVE by graduation).
  const liveAuthorizedCount = useMemo(
    () => allRows.filter((r) => r.is_live_authorized).length,
    [allRows],
  )

  /* ─── Derived: filter option lists ─── */
  const templateOptions = useMemo(
    () =>
      uniqueSorted(
        allRows
          .map((r) => r.template_name ?? r.metadata?.template_name)
          .filter((t): t is string => typeof t === 'string' && t.length > 0),
      ),
    [allRows],
  )
  const regimeOptions = useMemo(
    () =>
      uniqueSorted(
        allRows
          .map(
            (r) => r.market_regime ?? r.metadata?.market_regime ?? r.metadata?.activation_regime,
          )
          .filter((r): r is string => typeof r === 'string' && r.length > 0),
      ),
    [allRows],
  )
  const categoryOptions = useMemo(
    () =>
      uniqueSorted(
        allRows
          .map((r) => r.strategy_category)
          .filter((c): c is string => typeof c === 'string' && c.length > 0),
      ),
    [allRows],
  )
  const typeOptions = useMemo(
    () =>
      uniqueSorted(
        allRows
          .map((r) => r.strategy_type)
          .filter((t): t is string => typeof t === 'string' && t.length > 0),
      ),
    [allRows],
  )

  /* ─── Filtering ─── */
  const rows = useMemo(() => applyFilters(allRows, filters), [allRows, filters])

  /* ─── URL sync ─── */
  useEffect(() => {
    const next = syncFiltersToUrl(filters, params)
    if (selectedId) next.set('selected', selectedId)
    else next.delete('selected')
    if (next.toString() !== params.toString()) {
      setParams(next, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters, selectedId])

  /* ─── Actions ─── */
  const activate = useActivateStrategy()
  const deactivate = useDeactivateStrategy()
  const retire = useRetireStrategy()
  const deletePermanent = useDeleteStrategyPermanent()
  const backtest = useStrategyBacktest()

  const handleRowMenu = useCallback(
    (action: Parameters<React.ComponentProps<typeof StrategyDetailPanel>['onAction']>[0] | 'detail', row: StrategyRow) => {
      if (action === 'detail') {
        setSelectedId(row.id)
        return
      }
      setConfirmAction({ kind: action as any, target: row })
    },
    [],
  )

  const columns = useMemo(
    () => buildStrategyColumns({ onRowMenuAction: handleRowMenu }),
    [handleRowMenu],
  )

  const selectedIds = useMemo(
    () => Object.keys(rowSelection).filter((id) => rowSelection[id]),
    [rowSelection],
  )
  const selectedStrategies = useMemo(
    () => allRows.filter((r) => selectedIds.includes(r.id)),
    [allRows, selectedIds],
  )

  const runSingleAction = async (
    kind: Exclude<Parameters<typeof handleRowMenu>[0], 'detail'>,
    target: StrategyRow,
  ) => {
    try {
      if (kind === 'activate') {
        await activate.mutateAsync({
          strategyId: target.id,
          mode,
          allocation_percent: target.allocation_percent || 5.0,
        })
        toast.success(`Activated ${target.name}`)
      } else if (kind === 'deactivate') {
        await deactivate.mutateAsync({ strategyId: target.id, mode })
        toast.success(`Deactivated ${target.name}`)
      } else if (kind === 'retire') {
        await retire.mutateAsync({ strategyId: target.id, mode })
        toast.success(`Retired ${target.name}`)
      } else if (kind === 'delete-permanent') {
        await deletePermanent.mutateAsync({ strategyId: target.id, mode })
        toast.success(`Permanently deleted ${target.name}`)
        if (selectedId === target.id) setSelectedId(null)
      } else if (kind === 'backtest') {
        toast.success(`Backtest started — ${target.name}`)
        await backtest.mutateAsync({ strategyId: target.id })
        toast.success(`Backtest complete — ${target.name}`)
      }
    } catch (err) {
      notifyError(err, kind)
    } finally {
      setConfirmAction(null)
    }
  }

  const runBulk = async (kind: 'activate' | 'retire') => {
    const results = await Promise.allSettled(
      selectedStrategies.map((s) =>
        kind === 'activate'
          ? activate.mutateAsync({
              strategyId: s.id,
              mode,
              allocation_percent: s.allocation_percent || 5.0,
            })
          : retire.mutateAsync({ strategyId: s.id, mode }),
      ),
    )
    const succeeded = results.filter((r) => r.status === 'fulfilled').length
    const failed = results.length - succeeded
    if (failed === 0) {
      toast.success(
        `${kind === 'activate' ? 'Activated' : 'Retired'} ${succeeded} strategies`,
      )
    } else {
      toast.warning(
        `${succeeded} ${kind === 'activate' ? 'activated' : 'retired'}, ${failed} failed`,
      )
    }
    setRowSelection({})
    setConfirmBulk(null)
  }

  const handleExport = () => {
    const now = new Date().toISOString().replace(/[:.]/g, '-')
    downloadCsv(`alphacent-strategies-${mode}-${now}`, rows, strategyCsvColumns)
  }

  /* ─── Keyboard navigation ─── */
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const inField =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      if (inField) return
      if (e.metaKey || e.ctrlKey || e.altKey) return

      if (e.key === '/') {
        e.preventDefault()
        const input = document.querySelector<HTMLInputElement>('[data-library-search]')
        input?.focus()
        return
      }

      if (rows.length === 0) return
      if (e.key.toLowerCase() === 'j' || e.key.toLowerCase() === 'k') {
        e.preventDefault()
        const currentIdx = selectedId
          ? rows.findIndex((r) => r.id === selectedId)
          : -1
        const nextIdx =
          e.key.toLowerCase() === 'j'
            ? Math.min(rows.length - 1, currentIdx + 1)
            : Math.max(0, currentIdx - 1)
        if (rows[nextIdx]) setSelectedId(rows[nextIdx].id)
        return
      }

      if (e.key === 'Enter' && selectedId) {
        // Already open — no-op; could refocus detail panel here.
        return
      }

      if (e.key === 'c' && selectedIds.length === 2) {
        e.preventDefault()
        setCompareOpen(true)
        return
      }

      if ((e.key === '[' || e.key === ']') && selectedId) {
        e.preventDefault()
        setDetailSub((cur) => nextSubTab(cur, e.key === ']' ? 1 : -1))
        return
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [rows, selectedId, selectedIds.length])

  /* ─── Render ─── */
  if (strategiesQuery.isError) {
    const info = classifyError(strategiesQuery.error, 'strategy library')
    return (
      <ErrorState
        title="Couldn't load strategies"
        message={info.message}
        onRetry={() => strategiesQuery.refetch()}
      />
    )
  }

  const emptyLibrary = !strategiesQuery.isLoading && allRows.length === 0

  const tableContent = (
    <div className="flex flex-col h-full min-h-0" ref={tableBodyRef}>
      <LibraryStatusBar
        counts={pipelineQuery.counts}
        liveAuthorizedCount={liveAuthorizedCount}
        loading={pipelineQuery.isLoading}
        onStatusFilter={(status) =>
          setFilters((prev) => ({ ...prev, status: status as StrategyStatus | 'all' }))
        }
        activeStatus={filters.status}
      />
      <LibraryFilterBar
        filters={filters}
        onChange={setFilters}
        templateOptions={templateOptions}
        regimeOptions={regimeOptions}
        categoryOptions={categoryOptions}
        typeOptions={typeOptions}
        resultCount={rows.length}
        totalCount={allRows.length}
      />
      <LibraryBulkBar
        selectedCount={selectedIds.length}
        totalCount={allRows.length}
        canCompare={selectedIds.length === 2}
        onCompare={() => setCompareOpen(true)}
        onActivateSelected={() => setConfirmBulk('activate')}
        onRetireSelected={() => setConfirmBulk('retire')}
        onRefresh={() => strategiesQuery.refetch()}
        onExportCsv={handleExport}
        isActivating={activate.isPending}
        isRetiring={retire.isPending}
        isRefreshing={strategiesQuery.isFetching}
      />
      <div className="flex-1 min-h-0">
        {emptyLibrary ? (
          <EmptyState
            icon={Library}
            title="No strategies yet"
            description="Run your first autonomous cycle from Strategies → Cycle to propose, validate and activate strategies."
          />
        ) : (
          <DataTable<StrategyRow>
            data={rows}
            columns={columns}
            rowKey={(r) => r.id}
            loading={strategiesQuery.isLoading}
            sorting={{ state: sorting, onChange: setSorting }}
            selection={{
              mode: 'multi',
              selected: rowSelection,
              onChange: setRowSelection,
            }}
            activeRowId={selectedId}
            onRowClick={(r) => setSelectedId(r.id)}
            density="default"
            emptyState={
              <EmptyState
                icon={Library}
                title="No matches"
                description="Adjust filters or clear quick-pill selections to see more strategies."
              />
            }
          />
        )}
      </div>
    </div>
  )

  const detailPanel = selectedId ? (
    <StrategyDetailPanel
      strategyId={selectedId}
      onClose={() => setSelectedId(null)}
      onAction={(action, row) => handleRowMenu(action, row)}
      subTab={detailSub}
      onSubTabChange={setDetailSub}
    />
  ) : null

  return (
    <>
      {selectedId ? (
        <ResizablePanelLayout
          layoutId="strategies.library"
          panels={[
            {
              id: 'library-main',
              defaultSize: 60,
              minSize: 40,
              content: tableContent,
            },
            {
              id: 'library-detail',
              defaultSize: 40,
              minSize: 24,
              maxSize: 60,
              content: detailPanel,
            },
          ]}
        />
      ) : (
        tableContent
      )}

      {/* Single-row confirm dialog */}
      <ConfirmDialog
        open={!!confirmAction}
        onOpenChange={(o) => !o && setConfirmAction(null)}
        title={confirmActionTitle(confirmAction?.kind)}
        description={confirmAction ? confirmActionCopy(confirmAction.kind, confirmAction.target) : ''}
        confirmLabel={confirmActionLabel(confirmAction?.kind)}
        confirmVariant={
          confirmAction?.kind === 'retire' || confirmAction?.kind === 'delete-permanent'
            ? 'destructive'
            : 'primary'
        }
        isLoading={
          (confirmAction?.kind === 'activate' && activate.isPending) ||
          (confirmAction?.kind === 'deactivate' && deactivate.isPending) ||
          (confirmAction?.kind === 'retire' && retire.isPending) ||
          (confirmAction?.kind === 'delete-permanent' && deletePermanent.isPending) ||
          (confirmAction?.kind === 'backtest' && backtest.isPending)
        }
        onConfirm={() => {
          if (!confirmAction) return
          void runSingleAction(confirmAction.kind, confirmAction.target)
        }}
      />

      {/* Bulk confirm dialog */}
      <ConfirmDialog
        open={!!confirmBulk}
        onOpenChange={(o) => !o && setConfirmBulk(null)}
        title={
          confirmBulk === 'activate'
            ? `Activate ${selectedIds.length} selected strategies`
            : `Retire ${selectedIds.length} selected strategies`
        }
        description={
          confirmBulk === 'activate'
            ? `Each strategy will be activated with its current allocation (or 5% default). This puts them into PAPER/LIVE rotation.`
            : `Retiring removes these strategies from the library and marks them RETIRED. Open positions are not closed automatically.`
        }
        confirmLabel={confirmBulk === 'activate' ? 'Activate' : 'Retire'}
        confirmVariant={confirmBulk === 'retire' ? 'destructive' : 'primary'}
        isLoading={activate.isPending || retire.isPending}
        onConfirm={() => {
          if (confirmBulk) void runBulk(confirmBulk)
        }}
      />

      <CompareDialog
        open={compareOpen}
        onOpenChange={setCompareOpen}
        left={selectedStrategies[0] ?? null}
        right={selectedStrategies[1] ?? null}
      />
    </>
  )
}

/* ─────────────────────────── helpers ─────────────────────────── */

function uniqueSorted(values: string[]): string[] {
  return Array.from(new Set(values)).sort((a, b) =>
    a.localeCompare(b, 'en-US', { sensitivity: 'base' }),
  )
}

function applyFilters(rows: StrategyRow[], filters: LibraryFilters): StrategyRow[] {
  const q = filters.search.trim().toLowerCase()
  return rows.filter((r) => {
    // Status — 'LIVE' filter matches is_live_authorized, not strategies.status
    if (filters.status !== 'all') {
      if (filters.status === 'LIVE') {
        if (!r.is_live_authorized) return false
      } else {
        const normalizedStatus = r.status === 'DEMO' ? 'PAPER' : r.status
        if (normalizedStatus !== filters.status) return false
      }
    }
    if (filters.template) {
      const t = r.template_name ?? r.metadata?.template_name
      if (t !== filters.template) return false
    }
    if (filters.regime) {
      const rg = r.market_regime ?? r.metadata?.market_regime ?? r.metadata?.activation_regime
      if (rg !== filters.regime) return false
    }
    if (filters.source !== 'all') {
      if ((r.source ?? r.metadata?.source) !== filters.source) return false
    }
    if (filters.category && r.strategy_category !== filters.category) return false
    if (filters.type && r.strategy_type !== filters.type) return false
    if (q) {
      const hay = [
        r.name,
        r.description,
        r.template_name,
        r.metadata?.template_name,
        ...(r.symbols ?? []),
      ]
        .filter((x): x is string => typeof x === 'string')
        .join(' ')
        .toLowerCase()
      if (!hay.includes(q)) return false
    }
    // Quick pills — ANDed.
    for (const pill of filters.quickPills) {
      if (pill === 'signals-today' && !hasSignalToday(r)) return false
      if (pill === 'idle-7d' && !isIdle7d(r)) return false
      if (pill === 'negative-live-pnl' && !hasNegativeLivePnl(r)) return false
      if (pill === 'graduation-eligible' && !isGraduationEligible(r)) return false
      if (pill === 'paper-20-plus' && !hasPaper20Plus(r)) return false
    }
    return true
  })
}

function confirmActionTitle(
  kind: 'activate' | 'deactivate' | 'retire' | 'delete-permanent' | 'backtest' | undefined,
): string {
  switch (kind) {
    case 'activate':
      return 'Activate strategy'
    case 'deactivate':
      return 'Deactivate strategy'
    case 'retire':
      return 'Retire strategy'
    case 'delete-permanent':
      return 'Permanently delete strategy'
    case 'backtest':
      return 'Run backtest'
    default:
      return ''
  }
}

function confirmActionLabel(
  kind: 'activate' | 'deactivate' | 'retire' | 'delete-permanent' | 'backtest' | undefined,
): string {
  switch (kind) {
    case 'activate':
      return 'Activate'
    case 'deactivate':
      return 'Deactivate'
    case 'retire':
      return 'Retire'
    case 'delete-permanent':
      return 'Delete permanently'
    case 'backtest':
      return 'Run backtest'
    default:
      return 'Confirm'
  }
}

function confirmActionCopy(
  kind: 'activate' | 'deactivate' | 'retire' | 'delete-permanent' | 'backtest',
  target: StrategyRow,
): string {
  const name = target.name
  switch (kind) {
    case 'activate':
      return `Activate ${name}? The strategy enters PAPER rotation with ${(target.allocation_percent || 5.0).toFixed(1)}% allocation.`
    case 'deactivate':
      return `Deactivate ${name}? The strategy stops generating signals. Open positions are not closed automatically.`
    case 'retire':
      return `Retire ${name}? This marks the strategy RETIRED and removes it from the active library. Open positions stay open.`
    case 'delete-permanent':
      return `Permanently delete ${name}? All traces of this strategy are removed from the database. This cannot be undone.`
    case 'backtest':
      return `Run a 90-day backtest on ${name}? Results persist to the strategy record and the status moves to BACKTESTED on success.`
  }
}
