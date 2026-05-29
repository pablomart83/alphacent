import { useRef, useState } from 'react'
import { toast } from 'sonner'
import {
  Activity,
  AlertCircle,
  ChevronRight,
  Edit2,
  Save,
  TrendingUp,
  XCircle,
} from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  EmptyState,
  Input,
  Label,
  Skeleton,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { ConvictionBar } from '@/components/trading/ConvictionBar'
import { notifyError } from '@/lib/errors'
import { cn, formatCurrency, formatNumber, formatTimestamp } from '@/lib/utils'
import {
  useLiveStrategies,
  useRetireLiveStrategy,
  useStrategy,
  useUpdateLiveStrategy,
  type LiveStrategyRow,
} from '../useStrategiesData'
import { useTradeJournal, type TradeJournalEntry } from '../../research/useResearchData'

/**
 * ActiveLiveTable — compact cards for each live-authorised pair.
 * Clicking a card calls onSelect to open the detail panel in the parent's
 * ResizablePanelLayout right pane (same pattern as GraduationCard).
 */
export function ActiveLiveTable({
  selectedId,
  onSelect,
}: {
  selectedId?: number | null
  onSelect?: (row: LiveStrategyRow | null) => void
}) {
  const query = useLiveStrategies()
  const retire = useRetireLiveStrategy()
  const [confirmRetire, setConfirmRetire] = useState<LiveStrategyRow | null>(null)

  const rows = query.data?.live_strategies ?? []

  const handleRetire = async () => {
    if (!confirmRetire) return
    try {
      await retire.mutateAsync({ liveId: confirmRetire.id })
      toast.success(
        `Retired ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}`,
      )
      if (selectedId === confirmRetire.id) onSelect?.(null)
      setConfirmRetire(null)
    } catch (err) {
      notifyError(err, 'retire live')
    }
  }

  return (
    <section className="flex flex-col gap-1.5 px-2 py-2 border-t border-[var(--border-subtle)]">
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Activity className="h-3.5 w-3.5 text-[var(--pnl-up)]" />
          <SectionLabel className="mb-0">Active live strategies</SectionLabel>
          <Badge variant="live" size="sm">{rows.length}</Badge>
        </div>
        <a
          href="/book/live?sub=divergence"
          className="text-[10px] text-[var(--accent-primary)] hover:underline"
        >
          Divergence heatmap →
        </a>
      </div>

      {/* Rows */}
      {query.isLoading ? (
        <Skeleton className="h-[44px]" />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Activity}
          title="No live authorisations"
          description="Approve a candidate from the queue above."
          className="py-3"
        />
      ) : (
        <div className="rounded-[3px] border border-[var(--border-subtle)] overflow-hidden">
          {/* Column headers */}
          <div className="grid items-center px-2 py-1 bg-[var(--bg-2)] border-b border-[var(--border-subtle)]"
            style={{ gridTemplateColumns: '1fr 52px 56px 52px 52px 52px 52px 44px 36px 28px' }}>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">Template</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">P&L</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Live Sh.</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Win%</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Ppr Sh.</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">SL/TP</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Conv.</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Since</span>
            <span className="text-[9px] uppercase tracking-wider text-[var(--text-3)] text-right">Div%</span>
            <span />
          </div>
          {/* Strategy rows */}
          {rows.map((row) => (
            <LiveStrategyRow
              key={row.id}
              row={row}
              isSelected={selectedId === row.id}
              onClick={() => onSelect?.(selectedId === row.id ? null : row)}
              onRetire={() => setConfirmRetire(row)}
            />
          ))}
        </div>
      )}

      <ConfirmDialog
        open={!!confirmRetire}
        onOpenChange={(o) => !o && setConfirmRetire(null)}
        title="Retire live authorisation"
        description={
          confirmRetire
            ? `Retire ${confirmRetire.template_name ?? confirmRetire.strategy_id} × ${confirmRetire.symbol}? Future signals stop firing live orders. Open live positions are NOT closed automatically.`
            : ''
        }
        confirmLabel="Retire"
        confirmVariant="destructive"
        isLoading={retire.isPending}
        onConfirm={handleRetire}
      />
    </section>
  )
}

/* ─────────────────────────── Table row ─────────────────────────── */

function LiveStrategyRow({
  row,
  isSelected,
  onClick,
  onRetire,
}: {
  row: LiveStrategyRow
  isSelected: boolean
  onClick: () => void
  onRetire: () => void
}) {
  const livePnl = (row.live_pnl ?? row.live_realized_pnl ?? 0) + (row.unrealized_pnl ?? 0)
  const hasPosition = (row.open_position_count ?? 0) > 0
  const liveTrades = row.live_trades ?? row.live_closed_trades ?? 0

  const div = row.divergence_pct
  const divColor =
    div == null ? 'var(--text-3)'
    : div < 50 ? 'var(--pnl-down)'
    : div < 80 ? 'var(--status-warning)'
    : 'var(--pnl-up)'

  const daysSince = row.activated_at
    ? Math.floor((Date.now() - new Date(row.activated_at).getTime()) / 86_400_000)
    : null

  // Signal status indicator (compact)
  const signalDot = (() => {
    const s = row.last_signal_status
    if (s === 'order_pending') return { color: 'var(--status-warning)', title: 'Order pending' }
    if (s === 'order_submitted') return { color: 'var(--pnl-up)', title: 'Order submitted' }
    if (s === 'blocked_conviction' || s === 'gate_blocked') return { color: 'var(--text-3)', title: row.last_signal_detail ?? 'Blocked' }
    if (s === 'signal_emitted') return { color: 'var(--accent-primary)', title: 'Signal emitted' }
    return null
  })()

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full text-left grid items-center px-2 py-1.5 transition-colors group border-b border-[var(--border-subtle)] last:border-b-0',
        isSelected
          ? 'bg-[color-mix(in_oklab,var(--pnl-up)_8%,var(--bg-1))]'
          : 'bg-[color-mix(in_oklab,var(--pnl-up)_2%,var(--bg-1))] hover:bg-[color-mix(in_oklab,var(--pnl-up)_5%,var(--bg-1))]',
      )}
      style={{ gridTemplateColumns: '1fr 52px 56px 52px 52px 52px 52px 44px 36px 28px' }}
    >
      {/* Template + symbol + signal dot */}
      <div className="flex items-center gap-1.5 min-w-0">
        <span className="h-1.5 w-1.5 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />
        {signalDot && (
          <span
            className="h-1.5 w-1.5 rounded-full shrink-0"
            style={{ backgroundColor: signalDot.color }}
            title={signalDot.title}
          />
        )}
        <span className="text-[11px] font-medium text-[var(--text-0)] truncate">
          {row.template_name ?? row.strategy_id}
        </span>
        <span className="mono text-[10px] font-bold text-[var(--pnl-up)] shrink-0">
          {row.symbol}
        </span>
        {hasPosition && (
          <span className="text-[9px] text-[var(--text-3)] shrink-0" title="Open position">●</span>
        )}
      </div>

      {/* P&L */}
      <span className={cn('mono text-[11px] text-right tabular-nums', livePnl >= 0 ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]')}>
        {livePnl >= 0 ? '+' : ''}{formatCurrency(livePnl, { precision: 0 })}
      </span>

      {/* Live Sharpe */}
      <span className={cn('mono text-[11px] text-right tabular-nums',
        row.live_sharpe == null ? 'text-[var(--text-3)]'
        : row.live_sharpe >= 1 ? 'text-[var(--pnl-up)]'
        : row.live_sharpe < 0 ? 'text-[var(--pnl-down)]'
        : 'text-[var(--text-1)]'
      )}>
        {row.live_sharpe != null ? formatNumber(row.live_sharpe, 2) : `${liveTrades}t`}
      </span>

      {/* Win % */}
      <span className={cn('mono text-[11px] text-right tabular-nums',
        row.live_win_rate == null ? 'text-[var(--text-3)]'
        : row.live_win_rate >= 55 ? 'text-[var(--pnl-up)]'
        : row.live_win_rate >= 40 ? 'text-[var(--text-1)]'
        : 'text-[var(--pnl-down)]'
      )}>
        {row.live_win_rate != null ? `${row.live_win_rate.toFixed(0)}%` : '—'}
      </span>

      {/* Paper Sharpe */}
      <span className={cn('mono text-[11px] text-right tabular-nums',
        row.current_paper_sharpe == null ? 'text-[var(--text-3)]'
        : row.current_paper_sharpe >= 1 ? 'text-[var(--pnl-up)]'
        : 'text-[var(--text-1)]'
      )}>
        {row.current_paper_sharpe != null ? formatNumber(row.current_paper_sharpe, 2) : '—'}
      </span>

      {/* SL/TP */}
      <span className="mono text-[10px] text-right text-[var(--text-2)] tabular-nums">
        {((row.sl_pct ?? 0.06) * 100).toFixed(0)}/{((row.tp_pct ?? 0.15) * 100).toFixed(0)}%
      </span>

      {/* Conviction min */}
      <span className="mono text-[11px] text-right text-[var(--text-2)] tabular-nums">
        {row.conviction_min ?? '—'}
      </span>

      {/* Since */}
      <span className="mono text-[10px] text-right text-[var(--text-3)] tabular-nums">
        {daysSince === 0 ? 'today' : daysSince != null ? `${daysSince}d` : '—'}
      </span>

      {/* Divergence */}
      <span className="mono text-[10px] text-right tabular-nums flex items-center justify-end gap-0.5" style={{ color: divColor }}>
        {div != null && div < 50 && <AlertCircle className="h-2.5 w-2.5 shrink-0" />}
        {div != null ? `${div.toFixed(0)}%` : '—'}
      </span>

      {/* Chevron */}
      <div className="flex items-center justify-end gap-1">
        <button
          type="button"
          onClick={(e) => { e.stopPropagation(); onRetire() }}
          className="text-[9px] text-[var(--text-3)] hover:text-[var(--pnl-down)] transition-colors px-0.5 opacity-0 group-hover:opacity-100"
          title="Retire"
        >
          ✕
        </button>
        <ChevronRight
          className={cn(
            'h-3 w-3 shrink-0 transition-transform',
            isSelected ? 'rotate-90 text-[var(--pnl-up)]' : 'text-[var(--text-3)] group-hover:text-[var(--text-1)]',
          )}
        />
      </div>
    </button>
  )
}

/* ─────────────────────────── Detail panel (side panel) ─────────────────────────── */

/**
 * LiveStrategyDetailPanel — renders in the right pane of ResizablePanelLayout.
 * Shows WF → Paper → Live phases with full historical detail + inline parameter editor.
 */
export function LiveStrategyDetailPanel({
  row,
  onClose,
  onRetire,
}: {
  row: LiveStrategyRow
  onClose: () => void
  onRetire: () => void
}) {
  const strategyQuery = useStrategy(row.strategy_id)
  const paperTradesQuery = useTradeJournal({
    strategyId: row.strategy_id,
    symbol: row.symbol,
    limit: 100,
  })
  const updateLive = useUpdateLiveStrategy()

  const [editing, setEditing] = useState(false)
  // committed holds the last-saved values so the read-mode display and
  // startEdit() both reflect what was actually saved, not the stale row prop
  // (which only updates after the query refetches ~60s later).
  const [committed, setCommitted] = useState({
    position_size: row.position_size ?? 900,
    sl_pct: row.sl_pct ?? 0.06,
    tp_pct: row.tp_pct ?? 0.15,
    conviction_min: row.conviction_min ?? 73,
  })
  const [editSize, setEditSize] = useState(committed.position_size)
  const [editSl, setEditSl] = useState(committed.sl_pct * 100)
  const [editTp, setEditTp] = useState(committed.tp_pct * 100)
  const [editConviction, setEditConviction] = useState(committed.conviction_min)

  // Reset all local state when the selected strategy changes.
  // The panel is not remounted on row switch — it receives a new row prop —
  // so without this the previous strategy's committed/edit values bleed through.
  const prevRowId = useRef(row.id)
  if (prevRowId.current !== row.id) {
    prevRowId.current = row.id
    const next = {
      position_size: row.position_size ?? 900,
      sl_pct: row.sl_pct ?? 0.06,
      tp_pct: row.tp_pct ?? 0.15,
      conviction_min: row.conviction_min ?? 73,
    }
    setCommitted(next)
    setEditSize(next.position_size)
    setEditSl(next.sl_pct * 100)
    setEditTp(next.tp_pct * 100)
    setEditConviction(next.conviction_min)
    setEditing(false)
  }

  const startEdit = () => {
    setEditSize(committed.position_size)
    setEditSl(committed.sl_pct * 100)
    setEditTp(committed.tp_pct * 100)
    setEditConviction(committed.conviction_min)
    setEditing(true)
  }

  const handleSave = async () => {
    try {
      await updateLive.mutateAsync({
        liveId: row.id,
        body: { position_size: editSize, sl_pct: editSl / 100, tp_pct: editTp / 100, conviction_min: editConviction },
      })
      // Update committed immediately so read-mode and next Edit reflect the new values
      // without waiting for the 60s query refetch.
      setCommitted({ position_size: editSize, sl_pct: editSl / 100, tp_pct: editTp / 100, conviction_min: editConviction })
      toast.success(`Parameters updated — ${row.template_name ?? row.strategy_id} × ${row.symbol}`, {
        description: `$${editSize.toFixed(0)} · SL ${editSl.toFixed(1)}% · TP ${editTp.toFixed(1)}% · C≥${editConviction}`,
      })
      setEditing(false)
    } catch (err) {
      notifyError(err, 'update live strategy')
    }
  }

  const strategy = strategyQuery.data
  const wf = strategy?.walk_forward_results ?? null
  const paperTrades = paperTradesQuery.data?.trades ?? []

  const paperStats = paperTrades.reduce(
    (acc: { total: number; count: number; wins: number; holdHours: number[]; best: number; worst: number }, t) => {
      if (t.pnl != null) {
        acc.total += t.pnl; acc.count++
        if (t.pnl > 0) acc.wins++
        if (t.pnl > acc.best) acc.best = t.pnl
        if (t.pnl < acc.worst) acc.worst = t.pnl
      }
      if (t.hold_time_hours != null) acc.holdHours.push(t.hold_time_hours)
      return acc
    },
    { total: 0, count: 0, wins: 0, holdHours: [], best: 0, worst: 0 },
  )
  const paperWinRate = paperStats.count > 0 ? (paperStats.wins / paperStats.count) * 100 : null
  const avgHoldHours = paperStats.holdHours.length > 0
    ? paperStats.holdHours.reduce((a, b) => a + b, 0) / paperStats.holdHours.length : null
  const avgPnlPerTrade = paperStats.count > 0 ? paperStats.total / paperStats.count : null
  const sortedByEntry = [...paperTrades].sort((a, b) => (b.entry_time ?? '').localeCompare(a.entry_time ?? ''))
  const lastOpened = sortedByEntry[0]?.entry_time ?? null
  const lastClosed = sortedByEntry.find(t => t.exit_time)?.exit_time ?? null

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      {/* Header */}
      <div className="flex items-start justify-between gap-2 px-3 py-2.5 border-b border-[var(--border-subtle)] shrink-0">
        <div className="min-w-0">
          <div className="flex items-center gap-2 mb-0.5">
            <span className="h-2 w-2 rounded-full bg-[var(--pnl-up)] animate-pulse shrink-0" />
            <span className="font-semibold text-[13px] text-[var(--text-0)] truncate">
              {row.template_name ?? row.strategy_id}
            </span>
            <span className="mono text-[12px] font-bold text-[var(--pnl-up)] shrink-0">
              {row.symbol}
            </span>
            <Badge variant="live" size="sm">LIVE</Badge>
          </div>
          <div className="text-[10px] text-[var(--text-3)] mono ml-4">
            Authorised {formatTimestamp(row.activated_at, 'short')}
          </div>
        </div>
        <div className="flex items-center gap-1 shrink-0">
          {!editing && (
            <Button size="sm" variant="secondary" className="text-[11px] h-6 gap-1" onClick={startEdit}>
              <Edit2 className="h-3 w-3" />Edit
            </Button>
          )}
          <Button size="sm" variant="ghost" className="text-[var(--pnl-down)] hover:text-[var(--pnl-down)] text-[11px] h-6" onClick={onRetire}>
            Retire
          </Button>
          <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
            <XCircle className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      {/* Scrollable body */}
      <div className="flex-1 min-h-0 overflow-auto px-3 py-3 space-y-3">

        {/* CIO Parameters — always visible, editable */}
        <PhaseSection label="CIO Parameters" color="var(--account-live)" badge="$">
          {editing ? (
            <div className="space-y-3">
              <div className="grid grid-cols-2 gap-2">
                <EditField label="Position size ($)" value={editSize} onChange={setEditSize} min={100} max={5000} step={50} suffix="$" hint="Real dollars per order" />
                <EditField label="Conviction min" value={editConviction} onChange={setEditConviction} min={50} max={100} step={1} suffix="" hint="Min score to fire live order" />
                <EditField label="Stop-loss %" value={editSl} onChange={setEditSl} min={0.5} max={25} step={0.5} suffix="%" hint="Applied at order time" />
                <EditField label="Take-profit %" value={editTp} onChange={setEditTp} min={1} max={80} step={0.5} suffix="%" hint="Applied at order time" />
              </div>
              <div className="flex items-center gap-2 pt-1">
                <Button size="sm" variant="primary" className="gap-1.5 bg-[var(--pnl-up)] hover:brightness-110" onClick={handleSave} loading={updateLive.isPending}>
                  <Save className="h-3 w-3" />Save changes
                </Button>
                <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
                <span className="text-[9px] text-[var(--text-3)] ml-auto">Takes effect on next signal cycle</span>
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-1.5">
              <Metric label="Size (real)" value={`$${committed.position_size.toFixed(0)}`} tone="neutral" />
              <Metric label="SL" value={`${(committed.sl_pct * 100).toFixed(1)}%`} tone="neutral" />
              <Metric label="TP" value={`${(committed.tp_pct * 100).toFixed(1)}%`} tone="neutral" />
              <Metric label="Conv. min" value={String(committed.conviction_min)} tone="neutral" />
            </div>
          )}
        </PhaseSection>

        {/* Phase tabs */}
        <PhaseTabs
          wfContent={
            strategyQuery.isLoading ? (
              <Skeleton className="h-[52px]" />
            ) : wf ? (
              <div className="grid grid-cols-3 gap-1.5">
                <Metric label="Test Sharpe" value={wf.test_sharpe != null ? formatNumber(wf.test_sharpe, 2) : '—'} tone={wf.test_sharpe != null && wf.test_sharpe >= 1 ? 'up' : 'neutral'} />
                <Metric label="Train Sharpe" value={wf.train_sharpe != null ? formatNumber(wf.train_sharpe, 2) : '—'} />
                <Metric label="Test Win %" value={wf.test_win_rate != null ? `${(wf.test_win_rate * 100).toFixed(0)}%` : '—'} tone={wf.test_win_rate != null && wf.test_win_rate >= 0.55 ? 'up' : 'neutral'} />
                <Metric label="Test trades" value={wf.test_trades != null ? String(Math.round(wf.test_trades)) : '—'} />
                {wf.test_return != null && <Metric label="Test return" value={`${(wf.test_return * 100).toFixed(1)}%`} tone={wf.test_return >= 0 ? 'up' : 'down'} />}
                {wf.test_max_drawdown != null && <Metric label="Test max DD" value={`${(Math.abs(wf.test_max_drawdown) * 100).toFixed(1)}%`} tone="down" />}
              </div>
            ) : (
              <p className="text-[11px] text-[var(--text-3)]">Walk-forward data not available.</p>
            )
          }
          paperContent={
            paperTradesQuery.isLoading ? (
              <Skeleton className="h-[52px]" />
            ) : (
              <>
                <div className="grid grid-cols-3 gap-1.5 mb-3">
                  <Metric label="Trades" value={String(row.current_paper_trades ?? paperStats.count)} />
                  <Metric label="Win %" value={row.current_paper_win_rate != null ? `${(row.current_paper_win_rate * 100).toFixed(0)}%` : paperWinRate != null ? `${paperWinRate.toFixed(0)}%` : '—'} tone={(row.current_paper_win_rate ?? (paperWinRate != null ? paperWinRate / 100 : null)) != null && ((row.current_paper_win_rate ?? 0) >= 0.55 || (paperWinRate ?? 0) >= 55) ? 'up' : 'neutral'} />
                  <Metric label="Total P&L" value={formatCurrency(row.current_paper_pnl ?? paperStats.total, { signed: true, precision: 0 })} tone={(row.current_paper_pnl ?? paperStats.total) >= 0 ? 'up' : 'down'} />
                  <Metric label="Sharpe" value={row.current_paper_sharpe != null ? formatNumber(row.current_paper_sharpe, 2) : '—'} tone={row.current_paper_sharpe != null && row.current_paper_sharpe >= 1 ? 'up' : 'neutral'} />
                  <Metric label="Avg P&L/trade" value={avgPnlPerTrade != null ? formatCurrency(avgPnlPerTrade, { signed: true, precision: 0 }) : '—'} tone={avgPnlPerTrade != null ? (avgPnlPerTrade >= 0 ? 'up' : 'down') : 'neutral'} />
                  <Metric label="Avg hold" value={avgHoldHours != null ? (avgHoldHours < 48 ? `${avgHoldHours.toFixed(0)}h` : `${(avgHoldHours / 24).toFixed(1)}d`) : '—'} />
                  <Metric label="Best trade" value={paperStats.count > 0 ? formatCurrency(paperStats.best, { signed: true, precision: 0 }) : '—'} tone="up" />
                  <Metric label="Worst trade" value={paperStats.count > 0 ? formatCurrency(paperStats.worst, { signed: true, precision: 0 }) : '—'} tone="down" />
                  <Metric label="Last opened" value={lastOpened ? formatTimestamp(lastOpened, 'date') : '—'} />
                  <Metric label="Last closed" value={lastClosed ? formatTimestamp(lastClosed, 'date') : '—'} />
                </div>
                {paperTrades.length > 0 && <TradeTable trades={paperTrades.slice(0, 30)} label="Paper trades (last 30)" />}
              </>
            )
          }
          liveContent={
            <>
              <div className="grid grid-cols-3 gap-1.5 mb-3">
                <Metric label="Total trades" value={String(row.live_trades ?? row.live_closed_trades ?? 0)} />
                <Metric label="Open" value={String(row.live_open_trades ?? row.open_position_count ?? 0)} tone={(row.live_open_trades ?? row.open_position_count ?? 0) > 0 ? 'up' : 'neutral'} />
                <Metric label="Closed" value={String(row.live_closed_trades ?? 0)} />
                <Metric label="Total P&L" value={(row.live_pnl ?? 0) !== 0 ? formatCurrency(row.live_pnl ?? 0, { signed: true, precision: 0 }) : (row.live_realized_pnl ?? 0) !== 0 ? formatCurrency(row.live_realized_pnl ?? 0, { signed: true, precision: 0 }) : 'Waiting'} tone={(row.live_pnl ?? row.live_realized_pnl ?? 0) >= 0 ? 'up' : 'down'} />
                <Metric label="Realised" value={row.live_realized_pnl != null ? formatCurrency(row.live_realized_pnl, { signed: true, precision: 0 }) : '—'} tone={row.live_realized_pnl != null ? (row.live_realized_pnl >= 0 ? 'up' : 'down') : 'neutral'} />
                <Metric label="Unrealised" value={row.unrealized_pnl != null && row.unrealized_pnl !== 0 ? formatCurrency(row.unrealized_pnl, { signed: true, precision: 0 }) : '—'} tone={row.unrealized_pnl != null ? (row.unrealized_pnl >= 0 ? 'up' : 'down') : 'neutral'} />
                <Metric label="Win rate" value={row.live_win_rate != null ? `${row.live_win_rate.toFixed(0)}%` : '—'} tone={row.live_win_rate != null ? (row.live_win_rate >= 55 ? 'up' : row.live_win_rate >= 40 ? 'neutral' : 'down') : 'neutral'} />
                <Metric label="Avg P&L/trade" value={row.live_avg_pnl != null ? formatCurrency(row.live_avg_pnl, { signed: true, precision: 0 }) : '—'} tone={row.live_avg_pnl != null ? (row.live_avg_pnl >= 0 ? 'up' : 'down') : 'neutral'} />
                <Metric label="Sharpe" value={row.live_sharpe != null ? formatNumber(row.live_sharpe, 2) : '—'} tone={row.live_sharpe != null && row.live_sharpe >= 1 ? 'up' : row.live_sharpe != null && row.live_sharpe < 0 ? 'down' : 'neutral'} />
                {row.live_best_trade != null && <Metric label="Best trade" value={formatCurrency(row.live_best_trade, { signed: true, precision: 0 })} tone="up" />}
                {row.live_worst_trade != null && <Metric label="Worst trade" value={formatCurrency(row.live_worst_trade, { signed: true, precision: 0 })} tone="down" />}
                {row.live_avg_hold_hours != null && <Metric label="Avg hold" value={row.live_avg_hold_hours < 48 ? `${row.live_avg_hold_hours.toFixed(0)}h` : `${(row.live_avg_hold_hours / 24).toFixed(1)}d`} />}
                {row.live_last_opened && <Metric label="Last opened" value={formatTimestamp(row.live_last_opened, 'date')} />}
                {row.live_last_closed && <Metric label="Last closed" value={formatTimestamp(row.live_last_closed, 'date')} />}
                {row.divergence_pct != null && <Metric label="Tracking" value={`${row.divergence_pct.toFixed(0)}%`} tone={row.divergence_pct >= 80 ? 'up' : row.divergence_pct >= 50 ? 'neutral' : 'down'} />}
                {(row.open_position_count ?? 0) > 0 && row.open_position_entry != null && (
                  <>
                    <Metric label="Entry" value={formatCurrency(row.open_position_entry, { precision: 2 })} />
                    {row.open_position_current != null && <Metric label="Current" value={formatCurrency(row.open_position_current, { precision: 2 })} tone={row.open_position_current >= row.open_position_entry ? 'up' : 'down'} />}
                  </>
                )}
              </div>
              {(row.live_trades ?? 0) === 0 && (row.live_closed_trades ?? 0) === 0 && (row.open_position_count ?? 0) === 0 && (
                <div className="rounded-[3px] border border-[color-mix(in_oklab,var(--pnl-up)_20%,var(--border-subtle))] bg-[color-mix(in_oklab,var(--pnl-up)_4%,var(--bg-1))] px-2.5 py-2 text-[11px] text-[var(--text-2)] mb-3">
                  <TrendingUp className="h-3.5 w-3.5 inline mr-1.5 text-[var(--pnl-up)]" />
                  Gate open — next ENTER signal for{' '}
                  <span className="mono font-medium text-[var(--pnl-up)]">{row.symbol}</span>{' '}
                  with conviction ≥ {committed.conviction_min} fires a real order.
                </div>
              )}
              {(row.live_trade_history?.length ?? 0) > 0 && <LiveTradeTable trades={row.live_trade_history!} />}
              {row.last_signal_status && (
                <div className="mt-3">
                  <LastSignalStatus status={row.last_signal_status} detail={row.last_signal_detail} pendingOrder={row.pending_order} />
                </div>
              )}
            </>
          }
          convictionContent={
            <div className="space-y-1.5">
              <p className="text-[10px] text-[var(--text-3)]">
                Signals must score ≥ {committed.conviction_min} to trigger a live fill.
              </p>
              <ConvictionBar score={committed.conviction_min} size="default" showValue />
            </div>
          }
        />
      </div>
    </div>
  )
}

type PhaseTabId = 'wf' | 'paper' | 'live' | 'conviction'

const PHASE_TABS: Array<{ id: PhaseTabId; label: string; color: string }> = [
  { id: 'wf',         label: 'Walk-forward', color: 'var(--accent-primary)' },
  { id: 'paper',      label: 'Paper',        color: 'var(--accent-secondary)' },
  { id: 'live',       label: 'Live',         color: 'var(--pnl-up)' },
  { id: 'conviction', label: 'Gate',         color: 'var(--accent-primary)' },
]

function PhaseTabs({
  wfContent,
  paperContent,
  liveContent,
  convictionContent,
}: {
  wfContent: React.ReactNode
  paperContent: React.ReactNode
  liveContent: React.ReactNode
  convictionContent: React.ReactNode
}) {
  const [active, setActive] = useState<PhaseTabId>('live')

  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] overflow-hidden">
      {/* Tab bar */}
      <div className="flex border-b border-[var(--border-subtle)] bg-[var(--bg-2)]">
        {PHASE_TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            onClick={() => setActive(t.id)}
            className={cn(
              'flex-1 px-2 py-1.5 text-[10px] font-medium uppercase tracking-wide transition-colors',
              active === t.id
                ? 'border-b-2'
                : 'text-[var(--text-3)] hover:text-[var(--text-1)] border-b-2 border-transparent',
            )}
            style={active === t.id ? { borderBottomColor: t.color, color: t.color } : undefined}
          >
            {t.label}
          </button>
        ))}
      </div>
      {/* Tab content */}
      <div className="p-2.5">
        {active === 'wf'         && wfContent}
        {active === 'paper'      && paperContent}
        {active === 'live'       && liveContent}
        {active === 'conviction' && convictionContent}
      </div>
    </div>
  )
}

function PhaseSection({
  label,
  color,
  badge,
  children,
}: {
  label: string
  color: string
  badge: string
  children: React.ReactNode
}) {
  return (
    <section className="space-y-1.5">
      <div className="flex items-center gap-1.5">
        <span
          className="inline-flex items-center justify-center h-4 w-4 rounded-[2px] text-[8px] font-bold text-white shrink-0"
          style={{ backgroundColor: color }}
        >
          {badge}
        </span>
        <SectionLabel className="mb-0">{label}</SectionLabel>
      </div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2.5">
        {children}
      </div>
    </section>
  )
}

function Metric({
  label,
  value,
  tone = 'neutral',
}: {
  label: string
  value: string
  tone?: 'up' | 'down' | 'neutral'
}) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">{label}</div>
      <div
        className={cn(
          'mono tabular-nums text-[12px] font-semibold mt-0.5',
          tone === 'up' ? 'text-[var(--pnl-up)]' : tone === 'down' ? 'text-[var(--pnl-down)]' : 'text-[var(--text-0)]',
        )}
      >
        {value}
      </div>
    </div>
  )
}

function TradeTable({ trades, label }: { trades: TradeJournalEntry[]; label: string }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">{label}</div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] max-h-[200px] overflow-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
              <th className="text-left px-2 py-1">Entry</th>
              <th className="text-right px-2 py-1">P&L</th>
              <th className="text-right px-2 py-1">P&L %</th>
              <th className="text-right px-2 py-1">Hold</th>
              <th className="text-left px-2 py-1">Exit</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className="border-b border-[var(--border-subtle)] hover:bg-[var(--bg-hover)]">
                <td className="px-2 py-1 text-[var(--text-2)]">{formatTimestamp(t.entry_time, 'date')}</td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '')}>
                  {t.pnl != null ? formatCurrency(t.pnl, { signed: true, precision: 0 }) : '—'}
                </td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl_percent ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl_percent ?? 0) < 0 ? 'text-[var(--pnl-down)]' : '')}>
                  {t.pnl_percent != null ? `${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                  {t.hold_time_hours != null ? (t.hold_time_hours < 48 ? `${t.hold_time_hours.toFixed(0)}h` : `${(t.hold_time_hours / 24).toFixed(1)}d`) : '—'}
                </td>
                <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[90px]">
                  {t.exit_reason?.replace(/_/g, ' ') ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function LiveTradeTable({ trades }: { trades: NonNullable<LiveStrategyRow['live_trade_history']> }) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">Live trade history</div>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] max-h-[200px] overflow-auto">
        <table className="w-full text-[10px]">
          <thead>
            <tr className="text-[9px] uppercase tracking-wider text-[var(--text-3)] border-b border-[var(--border-subtle)]">
              <th className="text-left px-2 py-1">Entry</th>
              <th className="text-right px-2 py-1">P&L</th>
              <th className="text-right px-2 py-1">P&L %</th>
              <th className="text-right px-2 py-1">Hold</th>
              <th className="text-left px-2 py-1">Exit</th>
            </tr>
          </thead>
          <tbody>
            {trades.map((t) => (
              <tr key={t.id} className={cn('border-b border-[var(--border-subtle)]', t.is_open ? 'bg-[color-mix(in_oklab,var(--pnl-up)_5%,transparent)]' : 'hover:bg-[var(--bg-hover)]')}>
                <td className="px-2 py-1 text-[var(--text-2)]">
                  {t.entry_time ? formatTimestamp(t.entry_time, 'date') : '—'}
                  {t.is_open && <span className="ml-1 text-[8px] text-[var(--pnl-up)] font-bold">OPEN</span>}
                </td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl ?? 0) < 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-3)]')}>
                  {t.pnl != null ? formatCurrency(t.pnl, { signed: true, precision: 0 }) : t.is_open ? 'open' : '—'}
                </td>
                <td className={cn('px-2 py-1 text-right mono tabular-nums', (t.pnl_percent ?? 0) > 0 ? 'text-[var(--pnl-up)]' : (t.pnl_percent ?? 0) < 0 ? 'text-[var(--pnl-down)]' : 'text-[var(--text-3)]')}>
                  {t.pnl_percent != null ? `${t.pnl_percent >= 0 ? '+' : ''}${t.pnl_percent.toFixed(1)}%` : '—'}
                </td>
                <td className="px-2 py-1 text-right mono tabular-nums text-[var(--text-2)]">
                  {t.hold_time_hours != null ? (t.hold_time_hours < 48 ? `${t.hold_time_hours.toFixed(0)}h` : `${(t.hold_time_hours / 24).toFixed(1)}d`) : '—'}
                </td>
                <td className="px-2 py-1 text-[var(--text-2)] truncate max-w-[100px]" title={t.exit_reason ?? undefined}>
                  {t.exit_reason?.replace(/_/g, ' ') ?? (t.is_open ? '—' : '—')}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function EditField({
  label, value, onChange, min, max, step, suffix, hint,
}: {
  label: string; value: number; onChange: (v: number) => void
  min: number; max: number; step: number; suffix: string; hint?: string
}) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <div className="relative mt-1">
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min} max={max} step={step}
          className="h-7 mono tabular-nums pr-6 text-[11px]"
        />
        {suffix && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-3)] pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
      {hint && <p className="text-[9px] text-[var(--text-3)] mt-0.5">{hint}</p>}
    </div>
  )
}

function LastSignalStatus({
  status,
  detail,
  pendingOrder,
}: {
  status: string
  detail?: string | null
  pendingOrder?: {
    etoro_order_id?: string | null
    etoro_status?: string | null
    etoro_units?: number | null
    etoro_amount?: number | null
    age_mins?: number | null
    submitted_at?: string | null
  } | null
}) {
  const isBlocked = status.startsWith('blocked') || status === 'gate_blocked'
  const isPending = status === 'order_pending'
  const isSubmitted = status === 'order_submitted'
  const isNoSignal = status === 'no_signal_yet'

  const color = isPending || isSubmitted
    ? 'var(--pnl-up)'
    : isBlocked
      ? 'var(--status-warning)'
      : 'var(--text-3)'

  const icon = isPending || isSubmitted ? '⏳' : isBlocked ? '⚠' : isNoSignal ? '○' : '●'

  return (
    <div
      className="rounded-[3px] border px-2.5 py-2 text-[10px] space-y-1"
      style={{
        borderColor: `color-mix(in oklab, ${color} 25%, var(--border-subtle))`,
        backgroundColor: `color-mix(in oklab, ${color} 5%, var(--bg-1))`,
      }}
    >
      <div className="flex items-center gap-1.5" style={{ color: 'var(--text-2)' }}>
        <span style={{ color }}>{icon}</span>
        <span>{detail ?? status.replace(/_/g, ' ')}</span>
      </div>
      {isPending && pendingOrder && (
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 pl-4 text-[9px] text-[var(--text-3)] mono">
          {pendingOrder.etoro_status && (
            <span>eToro: <span className="text-[var(--text-1)]">{pendingOrder.etoro_status}</span></span>
          )}
          {pendingOrder.etoro_amount != null && (
            <span>Amount: <span className="text-[var(--text-1)]">${pendingOrder.etoro_amount.toFixed(0)}</span></span>
          )}
          {pendingOrder.etoro_units != null && (
            <span>Units: <span className="text-[var(--text-1)]">{pendingOrder.etoro_units.toFixed(4)}</span></span>
          )}
          {pendingOrder.etoro_order_id && (
            <span>ID: <span className="text-[var(--text-1)]">{pendingOrder.etoro_order_id}</span></span>
          )}
        </div>
      )}
    </div>
  )
}
