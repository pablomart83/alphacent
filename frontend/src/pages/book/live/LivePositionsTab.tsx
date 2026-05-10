import { useCallback, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ColumnDef, RowSelectionState, SortingState } from '@tanstack/react-table'
import { Download, Info, MoreHorizontal, RefreshCw } from 'lucide-react'
import {
  Badge,
  Button,
  Checkbox,
  ConfirmDialog,
  DataTable,
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
  EmptyState,
  ErrorState,
} from '@/components/primitives'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { classifyError, notifyError } from '@/lib/errors'
import { downloadCsv, type CsvColumn } from '@/lib/csv'
import { cn, formatCurrency, formatTimestamp } from '@/lib/utils'
import { toast } from 'sonner'
import {
  useCloseLivePosition,
  useLiveConfig,
  useLiveSummary,
  useOpenPositions,
  useSyncPositions,
  type PositionRow,
} from '../useBookData'
import { Inbox } from 'lucide-react'

function priceForSymbol(v: number | null | undefined, sym: string): string {
  if (v == null) return '—'
  if (/^[A-Z]{6}$/.test(sym.toUpperCase())) return v.toFixed(5)
  if (v < 1) return v.toFixed(6)
  if (v < 10) return v.toFixed(4)
  return v.toFixed(2)
}

export function LivePositionsTab() {
  const navigate = useNavigate()
  const openQuery = useOpenPositions('LIVE')
  const summaryQuery = useLiveSummary()
  const config = useLiveConfig()
  const closeMutation = useCloseLivePosition()
  const syncMutation = useSyncPositions()

  const mirror = config.data?.mirror_ratio ?? summaryQuery.data?.mirror_ratio ?? 0.1

  const [sorting, setSorting] = useState<SortingState>([
    { id: 'opened', desc: true },
  ])
  const [rowSelection, setRowSelection] = useState<RowSelectionState>({})
  const [closeTarget, setCloseTarget] = useState<PositionRow | null>(null)

  const rows = openQuery.data?.positions ?? []

  const handleClose = useCallback(
    async (row: PositionRow) => {
      try {
        const res = await closeMutation.mutateAsync(row.id)
        toast.success(res.message || `Close submitted — ${row.symbol}`)
      } catch (e) {
        notifyError(e, 'close live position')
      } finally {
        setCloseTarget(null)
      }
    },
    [closeMutation],
  )

  const columns = useMemo<ColumnDef<PositionRow>[]>(
    () => [
      {
        id: 'select',
        size: 32,
        header: ({ table }) => (
          <Checkbox
            aria-label="Select all"
            checked={
              table.getIsAllRowsSelected()
                ? true
                : table.getIsSomeRowsSelected()
                  ? 'indeterminate'
                  : false
            }
            onCheckedChange={(v) => table.toggleAllRowsSelected(!!v)}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        cell: ({ row }) => (
          <Checkbox
            aria-label={`Select ${row.original.symbol}`}
            checked={row.getIsSelected()}
            onCheckedChange={(v) => row.toggleSelected(!!v)}
            onClick={(e) => e.stopPropagation()}
          />
        ),
        enableSorting: false,
      },
      {
        id: 'symbol',
        header: 'Symbol',
        accessorKey: 'symbol',
        size: 90,
        cell: ({ row }) => (
          <span className="mono font-semibold text-[var(--text-0)]">{row.original.symbol}</span>
        ),
      },
      {
        id: 'strategy',
        header: 'Strategy',
        accessorKey: 'strategy_name',
        cell: ({ row }) => (
          <span
            className="truncate max-w-[200px] inline-block align-middle"
            title={row.original.strategy_name || ''}
          >
            {row.original.strategy_name || '—'}
          </span>
        ),
      },
      {
        id: 'side',
        header: 'Side',
        accessorFn: (r) => r.side,
        size: 60,
        cell: ({ row }) => {
          const up = (row.original.side || '').toUpperCase()
          const isShort = up.includes('SHORT') || up.includes('SELL')
          return (
            <Badge variant={isShort ? 'error' : 'success'} size="sm">
              {isShort ? 'Short' : 'Long'}
            </Badge>
          )
        },
      },
      {
        id: 'virtual_invested',
        header: 'Virtual inv.',
        accessorFn: (r) => r.invested_amount ?? r.quantity ?? 0,
        size: 100,
        cell: ({ row }) => (
          <span className="mono tabular-nums">
            {formatCurrency(row.original.invested_amount ?? row.original.quantity ?? 0, { precision: 0 })}
          </span>
        ),
      },
      {
        id: 'real_invested',
        header: 'Real inv.',
        accessorFn: (r) => (r.invested_amount ?? r.quantity ?? 0) * mirror,
        size: 90,
        cell: ({ row }) => {
          const v = (row.original.invested_amount ?? row.original.quantity ?? 0) * mirror
          return (
            <span className="mono tabular-nums text-[var(--text-2)]">
              {formatCurrency(v, { precision: 0 })}
            </span>
          )
        },
      },
      {
        id: 'entry',
        header: 'Entry',
        accessorKey: 'entry_price',
        size: 96,
        cell: ({ row }) => (
          <span className="mono tabular-nums text-[var(--text-2)]">
            {priceForSymbol(row.original.entry_price, row.original.symbol)}
          </span>
        ),
      },
      {
        id: 'current',
        header: 'Current',
        accessorKey: 'current_price',
        size: 96,
        cell: ({ row }) => (
          <span className="mono tabular-nums">
            {priceForSymbol(row.original.current_price, row.original.symbol)}
          </span>
        ),
      },
      {
        id: 'pnl_virtual',
        header: 'Virtual P&L',
        accessorKey: 'unrealized_pnl',
        size: 110,
        cell: ({ row }) => (
          <PnLNumber value={row.original.unrealized_pnl} format="currency" precision={0} size="sm" />
        ),
      },
      {
        id: 'pnl_real',
        header: 'Real P&L',
        accessorFn: (r) => (r.unrealized_pnl ?? 0) * mirror,
        size: 100,
        cell: ({ row }) => (
          <PnLNumber
            value={(row.original.unrealized_pnl ?? 0) * mirror}
            format="currency"
            precision={2}
            size="sm"
          />
        ),
      },
      {
        id: 'pnl_pct',
        header: '%',
        accessorKey: 'unrealized_pnl_percent',
        size: 80,
        cell: ({ row }) => (
          <PnLNumber value={row.original.unrealized_pnl_percent} format="percentage" precision={2} size="sm" />
        ),
      },
      {
        id: 'sl',
        header: () => (
          <span className="inline-flex items-center gap-1">
            SL
            <span
              className="inline-flex items-center justify-center h-[12px] px-1 rounded-[1px] bg-[var(--bg-active)] text-[var(--text-3)] text-[8px] uppercase tracking-wider"
              title="eToro LIVE API has no SL-update endpoint — our monitoring enforces it DB-side via market-close."
            >
              DB
            </span>
          </span>
        ),
        accessorKey: 'stop_loss',
        size: 110,
        cell: ({ row }) => {
          const v = row.original.stop_loss
          if (v == null) return <span className="mono text-[var(--text-3)]">—</span>
          return (
            <span className="mono tabular-nums text-[var(--text-2)]">
              {priceForSymbol(v, row.original.symbol)}
            </span>
          )
        },
      },
      {
        id: 'opened',
        header: 'Opened',
        accessorKey: 'opened_at',
        size: 130,
        cell: ({ row }) => (
          <span className="text-[var(--text-3)] text-[10px]">
            {formatTimestamp(row.original.opened_at, 'short')}
          </span>
        ),
      },
      {
        id: 'actions',
        header: '',
        size: 36,
        enableSorting: false,
        cell: ({ row }) => (
          <div className="flex items-center justify-end" onClick={(e) => e.stopPropagation()}>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button
                  type="button"
                  aria-label={`Actions for ${row.original.symbol}`}
                  className={cn(
                    'h-6 w-6 inline-flex items-center justify-center rounded-[2px]',
                    'text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
                  )}
                >
                  <MoreHorizontal className="h-3.5 w-3.5" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  onSelect={() => navigate(`/book/position/${encodeURIComponent(row.original.symbol)}`)}
                >
                  View detail
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => setCloseTarget(row.original)}
                  className="text-[var(--pnl-down)]"
                >
                  Close live position
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    [mirror, navigate],
  )

  const handleSync = async () => {
    try {
      const res = await syncMutation.mutateAsync('LIVE')
      toast.success(`Synced — ${res.synced} live positions`)
    } catch (e) {
      notifyError(e, 'sync live positions')
    }
  }

  const handleExport = () => {
    const cols: CsvColumn<PositionRow>[] = [
      { header: 'Symbol', value: (r) => r.symbol },
      { header: 'Strategy', value: (r) => r.strategy_name ?? '' },
      { header: 'Side', value: (r) => r.side },
      { header: 'Virtual invested', value: (r) => r.invested_amount ?? r.quantity ?? 0 },
      { header: 'Real invested', value: (r) => (r.invested_amount ?? r.quantity ?? 0) * mirror },
      { header: 'Entry', value: (r) => r.entry_price },
      { header: 'Current', value: (r) => r.current_price },
      { header: 'Virtual PnL', value: (r) => r.unrealized_pnl },
      { header: 'Real PnL', value: (r) => (r.unrealized_pnl ?? 0) * mirror },
      { header: 'PnL %', value: (r) => r.unrealized_pnl_percent },
      { header: 'SL (DB)', value: (r) => r.stop_loss ?? '' },
      { header: 'TP', value: (r) => r.take_profit ?? '' },
      { header: 'Opened', value: (r) => r.opened_at },
    ]
    const now = new Date().toISOString().replace(/[:.]/g, '-')
    downloadCsv(`alphacent-positions-LIVE-${now}`, rows, cols)
  }

  if (openQuery.isError) {
    const info = classifyError(openQuery.error, 'live positions')
    return (
      <ErrorState
        title="Couldn't load live positions"
        message={info.message}
        onRetry={() => openQuery.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0">
      {/* Honesty banner about DB-side SL enforcement */}
      <div className="flex items-start gap-2 px-3 py-1.5 bg-[var(--bg-2)] border-b border-[var(--border-subtle)] text-[11px] leading-[16px] text-[var(--text-2)]">
        <Info className="h-3.5 w-3.5 mt-[1px] shrink-0 text-[var(--accent-primary)]" />
        <span>
          eToro LIVE API has no SL-modification endpoint. Stop values are stored in our DB and
          enforced every 60 s by the monitoring service via market-close on breach. The initial
          SL set at order-open time is the outage backstop only — eToro may widen it (observed
          ~10% floor on BTC).
        </span>
      </div>

      <div className="flex items-center gap-2 px-2 py-1 border-b border-[var(--border-subtle)] bg-[var(--bg-1)]">
        <span className="text-[11px] text-[var(--text-3)]">
          {rows.length.toLocaleString('en-US')} live position{rows.length === 1 ? '' : 's'}
        </span>
        <div className="ml-auto flex items-center gap-1">
          <Button
            variant="ghost"
            size="sm"
            onClick={handleSync}
            loading={syncMutation.isPending}
            className="gap-1"
            title="Re-sync live positions from eToro"
          >
            <RefreshCw className="h-3 w-3" />
            Sync
          </Button>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleExport}
            className="gap-1"
          >
            <Download className="h-3 w-3" />
            CSV
          </Button>
        </div>
      </div>
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
              title="No live positions"
              description={
                openQuery.data
                  ? 'Live trading is armed but no approved pair has fired yet. Approved authorisations convert to real fills when their signals trigger.'
                  : 'Live positions will appear here once graduated (template, symbol) pairs start firing.'
              }
            />
          }
        />
      </div>

      <ConfirmDialog
        open={!!closeTarget}
        onOpenChange={(o) => !o && setCloseTarget(null)}
        title="Close live position"
        description={
          closeTarget
            ? `Close real ${closeTarget.symbol} (${closeTarget.side})? This submits a market close to eToro's live account — real capital is moved.`
            : ''
        }
        confirmLabel="Close position"
        confirmVariant="destructive"
        isLoading={closeMutation.isPending}
        onConfirm={() => {
          if (closeTarget) void handleClose(closeTarget)
        }}
      />
    </div>
  )
}
