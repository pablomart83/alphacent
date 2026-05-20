import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { AlertTriangle, Check, X as Reject, XCircle, Zap } from 'lucide-react'
import {
  Badge,
  Button,
  ConfirmDialog,
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
  Input,
  Label,
  Separator,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { PnLNumber } from '@/components/trading/PnLNumber'
import { RegimePill } from '@/components/trading/RegimePill'
import { notifyError } from '@/lib/errors'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import { useQuery } from '@tanstack/react-query'
import { api } from '@/services/api'
import {
  assetClassForSymbol,
  liveConvictionThresholdFor,
  useGraduateStrategy,
  useRejectGraduation,
  useStrategy,
  type GraduationQueueRow,
} from '../useStrategiesData'

interface GraduationCardProps {
  row: GraduationQueueRow
  onClose: () => void
  mirrorRatio?: number
  /** Default config — pulled from /config/live-trading if the caller has it. */
  defaults?: {
    position_size?: number
    sl_pct_equity?: number
    sl_pct_crypto?: number
    tp_pct_equity?: number
    tp_pct_crypto?: number
    conviction_threshold_equity?: number
    conviction_threshold_crypto?: number
    symbol_cap_pct?: number
    min_order_size?: number
    max_order_size?: number
  }
}

/**
 * GraduationCard — the single most important component in Sprint 7.
 *
 * Shown in a right-side drawer. Contains:
 *   · Evidence: KPI grid, conviction decomposition, regime spread
 *   · Config form: size / SL / TP / conviction_min / notes
 *   · Impact preview: exposed real $ given mirror ratio
 *   · Actions: Reject (with reason) · Approve
 *
 * Approval invalidates graduation-queue, live-strategies, live-divergence,
 * live-summary and strategies — wired via useGraduateStrategy.
 */
export function GraduationCard({
  row,
  onClose,
  mirrorRatio = 0.1,
  defaults,
}: GraduationCardProps) {
  const detailQuery = useStrategy(row.strategy_id)
  const graduate = useGraduateStrategy()
  const reject = useRejectGraduation()

  const meta = detailQuery.data?.metadata ?? null
  const assetClass = assetClassForSymbol(row.symbol, meta?.asset_class)
  const isCrypto = assetClass === 'crypto'

  // Fetch pipeline size estimate from backend
  const sizeEstimateQuery = useQuery({
    queryKey: ['size-estimate', row.strategy_id, row.symbol],
    queryFn: () =>
      api.get<{ recommended_size: number; account_equity: number; reason: string | null }>(
        `/strategies/${row.strategy_id}/size-estimate?symbol=${encodeURIComponent(row.symbol)}`
      ),
    staleTime: 60_000,
    retry: false,
  })
  const pipelineSize = sizeEstimateQuery.data?.recommended_size ?? null

  const convictionThreshold =
    (isCrypto
      ? defaults?.conviction_threshold_crypto
      : defaults?.conviction_threshold_equity) ??
    liveConvictionThresholdFor(assetClass)

  const defaultSize = defaults?.position_size ?? 500
  const defaultSl = (isCrypto ? defaults?.sl_pct_crypto : defaults?.sl_pct_equity) ?? (isCrypto ? 0.08 : 0.06)
  const defaultTp = (isCrypto ? defaults?.tp_pct_crypto : defaults?.tp_pct_equity) ?? (isCrypto ? 0.2 : 0.15)

  const [positionSize, setPositionSize] = useState<number>(defaultSize)
  const [slPct, setSlPct] = useState<number>(defaultSl * 100) // percentage UI
  const [tpPct, setTpPct] = useState<number>(defaultTp * 100)
  const [convictionMin, setConvictionMin] = useState<number>(convictionThreshold)
  const [notes, setNotes] = useState<string>('')

  const [confirmApproveOpen, setConfirmApproveOpen] = useState(false)
  const [rejectDialogOpen, setRejectDialogOpen] = useState(false)
  const [rejectNotes, setRejectNotes] = useState('')

  /* Reset fields when a new row is selected. */
  useEffect(() => {
    setPositionSize(defaultSize)
    setSlPct(defaultSl * 100)
    setTpPct(defaultTp * 100)
    setConvictionMin(convictionThreshold)
    setNotes('')
  }, [row.strategy_id, row.symbol, defaultSize, defaultSl, defaultTp, convictionThreshold])

  const virtualAmount = positionSize / mirrorRatio
  const minSize = (defaults?.min_order_size ?? 200) * mirrorRatio
  const maxSize = (defaults?.max_order_size ?? 1500) * mirrorRatio
  const symbolCapPctUi = (defaults?.symbol_cap_pct ?? 0.2) * 100

  const sizeWarning =
    positionSize < minSize
      ? `Below min order size $${minSize.toFixed(0)} real`
      : positionSize > maxSize
        ? `Above max order size $${maxSize.toFixed(0)} real`
        : null
  const slTpWarning =
    slPct <= 0 || slPct >= 100
      ? 'SL out of range'
      : tpPct <= 0 || tpPct >= 200
        ? 'TP out of range'
        : null

  const canApprove = !sizeWarning && !slTpWarning && positionSize > 0

  const regime = meta?.activation_regime ?? meta?.market_regime ?? null

  const handleApprove = async () => {
    try {
      await graduate.mutateAsync({
        strategyId: row.strategy_id,
        body: {
          symbol: row.symbol,
          position_size: positionSize,
          sl_pct: slPct / 100,
          tp_pct: tpPct / 100,
          conviction_min: convictionMin,
          notes: notes.trim() || undefined,
        },
      })
      toast.success(`${row.template_name ?? row.strategy_name} × ${row.symbol} graduated to LIVE`, {
        description: `$${positionSize.toFixed(0)} real · $${virtualAmount.toFixed(0)} virtual per order · conviction ≥ ${convictionMin}`,
      })
      setConfirmApproveOpen(false)
      onClose()
    } catch (err) {
      notifyError(err, 'approve graduation')
      setConfirmApproveOpen(false)
    }
  }

  const handleReject = async () => {
    try {
      await reject.mutateAsync({
        strategyId: row.strategy_id,
        body: {
          symbol: row.symbol,
          notes: rejectNotes.trim() || undefined,
        },
      })
      toast.success(`Rejected ${row.template_name ?? row.strategy_name} × ${row.symbol}`, {
        description: '14-day cooldown applied',
      })
      setRejectDialogOpen(false)
      onClose()
    } catch (err) {
      notifyError(err, 'reject graduation')
    }
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      {/* Header */}
      <header className="shrink-0 flex items-start justify-between gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <h3
              className="text-[14px] font-semibold text-[var(--text-0)] truncate"
              title={row.template_name ?? row.strategy_name}
            >
              {row.template_name ?? row.strategy_name}
            </h3>
            <span className="text-[var(--text-3)]">×</span>
            <span className="mono text-[14px] font-semibold text-[var(--text-0)]">
              {row.symbol}
            </span>
            {regime && <RegimePill regime={regime} size="sm" />}
          </div>
          <p className="text-[10px] text-[var(--text-3)] mt-0.5">
            Since {row.first_paper_trade?.slice(0, 10) ?? 'first paper trade'} · {row.paper_trades}{' '}
            paper trades
          </p>
        </div>
        <Button size="icon-sm" variant="ghost" onClick={onClose} aria-label="Close">
          <XCircle className="h-3.5 w-3.5" />
        </Button>
      </header>

      {/* Body */}
      <div className="flex-1 min-h-0 overflow-auto px-3 py-2 space-y-4">
        <EvidenceKpis row={row} />

        <ConvictionDistribution meta={meta} threshold={convictionThreshold} />

        <Separator />

        <ConfigForm
          positionSize={positionSize}
          onPositionSizeChange={setPositionSize}
          slPct={slPct}
          onSlPctChange={setSlPct}
          tpPct={tpPct}
          onTpPctChange={setTpPct}
          convictionMin={convictionMin}
          onConvictionMinChange={setConvictionMin}
          notes={notes}
          onNotesChange={setNotes}
          sizeWarning={sizeWarning}
          slTpWarning={slTpWarning}
          sizeRange={{ min: minSize, max: maxSize }}
          pipelineSize={pipelineSize}
        />

        <ImpactPreview
          positionSize={positionSize}
          virtualAmount={virtualAmount}
          mirrorRatio={mirrorRatio}
          symbolCapPctUi={symbolCapPctUi}
          convictionMin={convictionMin}
          slPct={slPct}
          tpPct={tpPct}
        />
      </div>

      {/* Action bar */}
      <footer className="shrink-0 flex items-center justify-between gap-2 border-t border-[var(--border-subtle)] px-3 py-2 bg-[var(--bg-1)]">
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setRejectDialogOpen(true)}
          disabled={graduate.isPending}
          className="gap-1.5"
        >
          <Reject className="h-3.5 w-3.5" />
          Reject
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setConfirmApproveOpen(true)}
          disabled={!canApprove || graduate.isPending}
          loading={graduate.isPending}
          className="gap-1.5 bg-[var(--pnl-up)] hover:brightness-110"
        >
          <Check className="h-3.5 w-3.5" />
          Approve for live
        </Button>
      </footer>

      <ConfirmDialog
        open={confirmApproveOpen}
        onOpenChange={setConfirmApproveOpen}
        title="Approve for live trading"
        description={`Approving (${row.template_name ?? row.strategy_name}, ${row.symbol}) creates a live_strategies row. Every qualifying signal fires a real $${positionSize.toFixed(0)} eToro order ($${virtualAmount.toFixed(0)} virtual). Reversible via Retire.`}
        confirmLabel="Approve"
        confirmVariant="primary"
        isLoading={graduate.isPending}
        onConfirm={handleApprove}
      />

      <Dialog open={rejectDialogOpen} onOpenChange={setRejectDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Reject graduation</DialogTitle>
          </DialogHeader>
          <div className="space-y-2">
            <p className="text-[11px] text-[var(--text-2)]">
              Rejecting ({row.template_name ?? row.strategy_name}, {row.symbol}) applies a
              14-day cooldown. The pair will not re-appear in the queue.
            </p>
            <Label htmlFor="reject-notes" className="text-[10px] uppercase tracking-wider">
              Reason (optional)
            </Label>
            <textarea
              id="reject-notes"
              value={rejectNotes}
              onChange={(e) => setRejectNotes(e.target.value)}
              rows={3}
              placeholder="Paper Sharpe dropping in recent 30d; want more sample."
              className={cn(
                'w-full rounded-[3px] bg-[var(--bg-1)] border border-[var(--border-default)]',
                'px-2 py-1.5 text-[11px] text-[var(--text-0)]',
                'focus:outline-2 focus:outline-[var(--border-focus)]',
              )}
            />
          </div>
          <DialogFooter>
            <Button variant="ghost" size="sm" onClick={() => setRejectDialogOpen(false)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={handleReject}
              loading={reject.isPending}
            >
              Confirm reject
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

/* ──────────────────────────── sub-components ──────────────────────────── */

function EvidenceKpis({ row }: { row: GraduationQueueRow }) {
  return (
    <section>
      <SectionLabel>Paper performance</SectionLabel>
      <div className="grid grid-cols-2 gap-2">
        <Kpi
          label="Paper Sharpe"
          value={row.paper_sharpe != null ? row.paper_sharpe.toFixed(2) : '—'}
          emphasis={
            row.paper_sharpe != null && row.paper_sharpe >= 1.0
              ? 'positive'
              : row.paper_sharpe != null && row.paper_sharpe < 0.5
                ? 'negative'
                : null
          }
        />
        <Kpi
          label="WF Sharpe (expected)"
          value={row.wf_sharpe != null ? row.wf_sharpe.toFixed(2) : '—'}
        />
        <Kpi
          label="Qualification ratio"
          value={
            row.qualification_ratio != null
              ? `${(row.qualification_ratio * 100).toFixed(0)}%`
              : '—'
          }
          emphasis={
            row.qualification_ratio != null && row.qualification_ratio >= 1.0
              ? 'positive'
              : row.qualification_ratio != null && row.qualification_ratio < 0.6
                ? 'negative'
                : null
          }
        />
        <Kpi
          label="Win rate"
          value={
            row.paper_win_rate != null
              ? `${(row.paper_win_rate * 100).toFixed(1)}%`
              : '—'
          }
          emphasis={
            row.paper_win_rate != null && row.paper_win_rate >= 0.55
              ? 'positive'
              : null
          }
        />
        <Kpi label="Trades" value={String(row.paper_trades)} />
        <Kpi
          label="Total P&L"
          value={
            row.paper_total_pnl != null ? (
              <PnLNumber
                value={row.paper_total_pnl}
                format="currency"
                precision={0}
                size="sm"
                showSign
              />
            ) : (
              '—'
            )
          }
        />
        <Kpi
          label="Avg P&L / trade"
          value={
            row.avg_paper_pnl_per_trade != null ? (
              <PnLNumber
                value={row.avg_paper_pnl_per_trade}
                format="currency"
                precision={2}
                size="sm"
                showSign
              />
            ) : row.paper_total_pnl != null && row.paper_trades > 0 ? (
              <PnLNumber
                value={row.paper_total_pnl / row.paper_trades}
                format="currency"
                precision={2}
                size="sm"
                showSign
              />
            ) : (
              '—'
            )
          }
          emphasis={
            (row.avg_paper_pnl_per_trade ?? (row.paper_total_pnl != null && row.paper_trades > 0 ? row.paper_total_pnl / row.paper_trades : null)) != null
              ? ((row.avg_paper_pnl_per_trade ?? row.paper_total_pnl! / row.paper_trades) > 0 ? 'positive' : 'negative')
              : null
          }
        />
        <StatSigKpi trades={row.paper_trades} winRate={row.paper_win_rate} />
      </div>
    </section>
  )
}

function Kpi({
  label,
  value,
  emphasis,
}: {
  label: string
  value: React.ReactNode
  emphasis?: 'positive' | 'negative' | null
}) {
  const color =
    emphasis === 'positive'
      ? 'var(--pnl-up)'
      : emphasis === 'negative'
        ? 'var(--pnl-down)'
        : 'var(--text-0)'
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)]">
        {label}
      </div>
      <div className="mono tabular-nums text-[14px] mt-0.5" style={{ color }}>
        {value}
      </div>
    </div>
  )
}

function ConvictionDistribution({
  meta,
  threshold,
}: {
  meta: Record<string, unknown> | null
  threshold: number
}) {
  const convictionScore = typeof meta?.conviction_score === 'number' ? meta.conviction_score : null
  const breakdown = (meta?.conviction_score_breakdown as Record<string, number | null> | null) ?? null

  if (convictionScore == null) {
    return (
      <section>
        <SectionLabel>Conviction</SectionLabel>
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 text-[10px] text-[var(--text-3)]">
          Strategy metadata doesn't include conviction_score yet. Live fills are still gated
          by the runtime conviction check at ≥ {threshold}.
        </div>
      </section>
    )
  }

  const segments = [
    { key: 'wf_edge', label: 'WF Edge', color: 'var(--pnl-up)', max: 40 },
    { key: 'signal_quality', label: 'Signal Quality', color: 'var(--accent-primary)', max: 25 },
    { key: 'regime_fit', label: 'Regime Fit', color: 'var(--regime-up)', max: 20 },
    { key: 'asset_tradability', label: 'Asset Tradability', color: 'var(--accent-ticker)', max: 15 },
    { key: 'fundamental', label: 'Fundamental', color: 'var(--accent-secondary)', max: 15 },
    { key: 'carry', label: 'Carry', color: 'var(--status-warning)', max: 5 },
    { key: 'crypto_cycle', label: 'Crypto Cycle', color: 'var(--regime-vol)', max: 5 },
    { key: 'sentiment', label: 'Sentiment', color: 'var(--text-2)', max: 1 },
    { key: 'factor', label: 'Factor', color: 'var(--pnl-up-flash)', max: 6 },
  ]

  const totalPositive = segments.reduce((sum, s) => {
    const v = breakdown?.[s.key] ?? 0
    return sum + Math.max(0, v)
  }, 0)

  return (
    <section>
      <SectionLabel>Conviction · threshold {threshold}</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-2">
        <div className="flex items-baseline gap-2">
          <span
            className="mono tabular-nums text-[20px] font-semibold"
            style={{
              color:
                convictionScore >= threshold
                  ? 'var(--pnl-up)'
                  : convictionScore >= threshold - 5
                    ? 'var(--status-warning)'
                    : 'var(--pnl-down)',
            }}
          >
            {convictionScore.toFixed(0)}
          </span>
          <span className="text-[10px] text-[var(--text-3)]">/ 100</span>
          {convictionScore >= threshold ? (
            <Badge variant="success" size="sm">
              passes live gate
            </Badge>
          ) : (
            <Badge variant="warning" size="sm">
              below {threshold}
            </Badge>
          )}
        </div>

        {breakdown && totalPositive > 0 ? (
          <div>
            <div className="relative h-2.5 rounded-[1px] bg-[var(--bg-0)] overflow-hidden flex">
              {segments.map((s) => {
                const v = Math.max(0, breakdown[s.key] ?? 0)
                const pct = (v / 100) * 100
                if (pct <= 0) return null
                return (
                  <div
                    key={s.key}
                    style={{ width: `${pct}%`, backgroundColor: s.color }}
                    title={`${s.label}: ${v.toFixed(1)}`}
                  />
                )
              })}
              <div
                className="absolute inset-y-0 w-[1px]"
                style={{
                  left: `${Math.max(0, Math.min(100, threshold))}%`,
                  backgroundColor: 'var(--text-0)',
                }}
                title={`Live threshold ${threshold}`}
              />
            </div>
            <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 mt-1.5">
              {segments.map((s) => {
                const v = breakdown[s.key]
                if (v == null) return null
                return (
                  <div
                    key={s.key}
                    className="inline-flex items-center gap-1 text-[10px]"
                    title={`${s.label}: ${v.toFixed(1)} / ${s.max}`}
                  >
                    <span
                      className="h-1.5 w-1.5 rounded-full shrink-0"
                      style={{ backgroundColor: s.color }}
                    />
                    <span className="text-[var(--text-2)] truncate">{s.label}</span>
                    <span className="mono tabular-nums text-[var(--text-1)] ml-auto">
                      {v.toFixed(1)}
                    </span>
                  </div>
                )
              })}
            </div>
          </div>
        ) : (
          <p className="text-[10px] text-[var(--text-3)]">
            Breakdown unavailable — conviction score recorded but component breakdown not
            persisted on this strategy.
          </p>
        )}
      </div>
    </section>
  )
}

interface ConfigFormProps {
  positionSize: number
  onPositionSizeChange: (v: number) => void
  slPct: number
  onSlPctChange: (v: number) => void
  tpPct: number
  onTpPctChange: (v: number) => void
  convictionMin: number
  onConvictionMinChange: (v: number) => void
  notes: string
  onNotesChange: (v: string) => void
  sizeWarning: string | null
  slTpWarning: string | null
  sizeRange: { min: number; max: number }
  pipelineSize: number | null
}

function ConfigForm({
  positionSize,
  onPositionSizeChange,
  slPct,
  onSlPctChange,
  tpPct,
  onTpPctChange,
  convictionMin,
  onConvictionMinChange,
  notes,
  onNotesChange,
  sizeWarning,
  slTpWarning,
  sizeRange,
  pipelineSize,
}: ConfigFormProps) {
  return (
    <section>
      <SectionLabel>Live config — CIO decision</SectionLabel>
      <div className="space-y-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2">

        {/* Pipeline recommendation banner */}
        {pipelineSize != null && (
          <div className="flex items-center gap-2 rounded-[2px] bg-[color-mix(in_oklab,var(--accent-primary)_8%,transparent)] border border-[color-mix(in_oklab,var(--accent-primary)_20%,transparent)] px-2 py-1.5">
            <Zap className="h-3 w-3 text-[var(--accent-primary)] shrink-0" />
            <span className="text-[10px] text-[var(--text-2)]">
              11-step pipeline recommends{' '}
              <span className="mono font-semibold text-[var(--text-0)]">
                ${pipelineSize.toFixed(0)}
              </span>
              {' '}real — CIO sets the final size below
            </span>
            <button
              type="button"
              onClick={() => onPositionSizeChange(pipelineSize)}
              className="ml-auto text-[9px] uppercase tracking-wider text-[var(--accent-primary)] hover:underline shrink-0"
            >
              Use
            </button>
          </div>
        )}

        <div>
          <div className="flex items-baseline justify-between">
            <Label className="text-[10px] uppercase tracking-wider">
              Position size (real $) — CIO approved
            </Label>
            <span className="mono tabular-nums text-[12px] text-[var(--text-0)]">
              ${positionSize.toFixed(0)}
            </span>
          </div>
          <input
            type="range"
            min={sizeRange.min}
            max={sizeRange.max}
            step={5}
            value={positionSize}
            onChange={(e) => onPositionSizeChange(Number(e.target.value))}
            className="w-full mt-1 accent-[var(--accent-primary)]"
          />
          <div className="flex justify-between text-[9px] text-[var(--text-3)] mono">
            <span>${sizeRange.min.toFixed(0)}</span>
            <span>${sizeRange.max.toFixed(0)}</span>
          </div>
          {sizeWarning && (
            <div className="flex items-center gap-1 text-[10px] text-[var(--status-warning)] mt-1">
              <AlertTriangle className="h-3 w-3" />
              {sizeWarning}
            </div>
          )}
          <p className="text-[9px] text-[var(--text-3)] mt-1">
            Real dollars invested per order. System converts to virtual (÷ mirror ratio) before sending to eToro.
          </p>
        </div>

        <div className="grid grid-cols-2 gap-2">
          <NumberField
            label="Stop-loss %"
            value={slPct}
            onChange={onSlPctChange}
            min={0.5}
            max={25}
            step={0.5}
            suffix="%"
          />
          <NumberField
            label="Take-profit %"
            value={tpPct}
            onChange={onTpPctChange}
            min={1}
            max={80}
            step={0.5}
            suffix="%"
          />
        </div>
        {slTpWarning && (
          <div className="flex items-center gap-1 text-[10px] text-[var(--status-warning)]">
            <AlertTriangle className="h-3 w-3" />
            {slTpWarning}
          </div>
        )}

        <NumberField
          label="Conviction min (live)"
          value={convictionMin}
          onChange={onConvictionMinChange}
          min={60}
          max={100}
          step={1}
          suffix=""
        />

        <div>
          <Label htmlFor="graduation-notes" className="text-[10px] uppercase tracking-wider">
            Notes
          </Label>
          <textarea
            id="graduation-notes"
            value={notes}
            onChange={(e) => onNotesChange(e.target.value)}
            rows={2}
            placeholder="CIO rationale, what you're watching for…"
            className={cn(
              'w-full mt-1 rounded-[3px] bg-[var(--bg-0)] border border-[var(--border-default)]',
              'px-2 py-1.5 text-[11px] text-[var(--text-0)]',
              'focus:outline-2 focus:outline-[var(--border-focus)]',
            )}
          />
        </div>
      </div>
    </section>
  )
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step,
  suffix,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min: number
  max: number
  step: number
  suffix?: string
}) {
  return (
    <div>
      <Label className="text-[10px] uppercase tracking-wider">{label}</Label>
      <div className="relative mt-1">
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min}
          max={max}
          step={step}
          className="h-7 mono tabular-nums pr-6 text-[11px]"
        />
        {suffix && (
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-3)] pointer-events-none">
            {suffix}
          </span>
        )}
      </div>
    </div>
  )
}

function ImpactPreview({
  positionSize,
  virtualAmount,
  mirrorRatio,
  symbolCapPctUi,
  convictionMin,
  slPct,
  tpPct,
}: {
  positionSize: number
  virtualAmount: number
  mirrorRatio: number
  symbolCapPctUi: number
  convictionMin: number
  slPct: number
  tpPct: number
}) {
  const maxLoss = positionSize * (slPct / 100)
  const maxGain = positionSize * (tpPct / 100)

  return (
    <section>
      <SectionLabel>Impact preview</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1 text-[11px]">
        <ImpactRow
          label="Per order"
          value={
            <span>
              <span className="mono text-[var(--account-live)]">${positionSize.toFixed(0)}</span>{' '}
              <span className="text-[var(--text-3)]">real</span>
              <span className="text-[var(--text-3)]"> → </span>
              <span className="mono">${virtualAmount.toFixed(0)}</span>{' '}
              <span className="text-[var(--text-3)]">
                virtual ({(mirrorRatio * 100).toFixed(0)}% mirror)
              </span>
            </span>
          }
        />
        <ImpactRow
          label="Max loss per order"
          value={
            <span className="mono text-[var(--pnl-down)]">
              -${maxLoss.toFixed(0)} real
            </span>
          }
        />
        <ImpactRow
          label="Target per order"
          value={
            <span className="mono text-[var(--pnl-up)]">
              +${maxGain.toFixed(0)} real
            </span>
          }
        />
        <ImpactRow
          label="Symbol cap"
          value={
            <span className="mono">
              ${(virtualAmount * (symbolCapPctUi / 100) * 10).toFixed(0)} virtual (
              {symbolCapPctUi.toFixed(0)}% of $10K)
            </span>
          }
        />
        <ImpactRow
          label="Signal gate"
          value={
            <span className="text-[var(--text-2)]">
              Fires only when conviction ≥{' '}
              <span className="mono text-[var(--text-0)]">{convictionMin}</span>
            </span>
          }
        />
      </div>
    </section>
  )
}

function ImpactRow({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span className="text-[var(--text-3)] uppercase tracking-wider text-[9px]">
        {label}
      </span>
      <span>{value}</span>
    </div>
  )
}

/* Silence unused formatter imports. */
export const __fmts = [formatCurrency, formatPercentage]

/* ──────────────────────────── statistical significance ──────────────────── */

/**
 * Compute one-sided binomial p-value: P(X >= k | n, p0=0.5).
 * Normal approximation — accurate enough for n >= 10.
 * H0: win rate <= 50% (coin flip). H1: win rate > 50%.
 */
function binomialPValue(wins: number, n: number, p0 = 0.5): number {
  if (n <= 0) return 1.0
  // Normal approximation with continuity correction
  const mean = n * p0
  const std = Math.sqrt(n * p0 * (1 - p0))
  if (std === 0) return wins > mean ? 0 : 1
  const z = (wins - 0.5 - mean) / std  // continuity correction
  // Standard normal CDF approximation (Abramowitz & Stegun 26.2.17)
  const t = 1 / (1 + 0.2316419 * Math.abs(z))
  const poly =
    t * (0.319381530 +
      t * (-0.356563782 +
        t * (1.781477937 +
          t * (-1.821255978 +
            t * 1.330274429))))
  const phi = (1 / Math.sqrt(2 * Math.PI)) * Math.exp(-0.5 * z * z) * poly
  // One-sided p-value: P(Z >= z)
  return z >= 0 ? phi : 1 - phi
}

/**
 * Statistical significance KPI tile.
 *
 * Shows the one-sided binomial p-value for the observed win rate vs H0: WR=50%.
 * This is NOT a gate — it's context for the CIO. The graduation gate is a
 * consistency check, not a significance test. At 15 trades / 55% WR, p ≈ 0.50.
 */
function StatSigKpi({
  trades,
  winRate,
}: {
  trades: number
  winRate?: number | null
}) {
  if (winRate == null || trades < 5) {
    return (
      <Kpi
        label="Stat significance"
        value="—"
        emphasis={null}
      />
    )
  }

  const wins = Math.round(trades * winRate)
  const p = binomialPValue(wins, trades)
  const pStr = p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`

  let label: string
  let emphasis: 'positive' | 'negative' | null = null
  if (p < 0.05) {
    label = `${pStr} ✓`
    emphasis = 'positive'
  } else if (p < 0.10) {
    label = `${pStr} ~`
    emphasis = null
  } else {
    label = pStr
    emphasis = null
  }

  return (
    <Kpi
      label="Stat significance"
      value={
        <span
          title={`One-sided binomial test (H₀: WR ≤ 50%). ${wins}/${trades} wins. p < 0.05 = significant, p < 0.10 = weak evidence. At 15 trades / 55% WR, p ≈ 0.50 — the graduation gate is a consistency check, not a significance test.`}
          className="cursor-help"
        >
          {label}
        </span>
      }
      emphasis={emphasis}
    />
  )
}
