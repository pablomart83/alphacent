import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Info } from 'lucide-react'
import { Card, Input, Label, Switch } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  usePaperTradingConfig,
  useUpdatePaperTradingConfig,
  type PaperTradingConfigShape,
} from '../useSettingsData'

/**
 * Paper trading config — the DEMO/research pipeline parameters.
 *
 * Paper trading has a different objective from live trading: data collection
 * for graduation decisions, not profitability. These parameters are deliberately
 * more permissive than live to maximise trade throughput and statistical coverage.
 *
 * Key design decisions documented here:
 * - Flat position sizing: every strategy gets equal data quality regardless of
 *   vol, drawdown, or conviction. The graduation gate is the quality filter.
 * - Lower conviction threshold: collect data on borderline strategies.
 * - Relaxed activation thresholds: WF Sharpe 0.5–1.0 is worth understanding.
 * - Disabled RPT/expectancy gates: data collection, not profitability optimisation.
 * - Interval-aware graduation min_trades: 1D fires ~1/month, 1H fires ~5/month.
 */
export function PaperTradingSettingsTab() {
  const cfg = usePaperTradingConfig()
  const update = useUpdatePaperTradingConfig()
  const initial = useMemo(() => (cfg.data ? extract(cfg.data) : null), [cfg.data])
  const [form, setForm] = useState<typeof initial>(null)

  useEffect(() => {
    if (initial) setForm(initial)
  }, [initial])

  const dirty = !!initial && !!form && JSON.stringify(initial) !== JSON.stringify(form)
  const changeCount = useMemo(() => {
    if (!initial || !form) return 0
    let n = 0
    for (const k of Object.keys(form) as Array<keyof typeof form>) {
      if (initial[k] !== form[k]) n += 1
    }
    return n
  }, [initial, form])

  const set = <K extends keyof Exclude<typeof form, null>>(
    k: K,
    v: Exclude<typeof form, null>[K],
  ) => {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev))
  }

  const onSave = async () => {
    if (!form) return
    try {
      await update.mutateAsync({
        flat_position_size: form.flat_position_size,
        conviction_threshold: form.conviction_threshold,
        conviction_threshold_crypto: form.conviction_threshold_crypto,
        conviction_threshold_alpha_edge: form.conviction_threshold_alpha_edge,
        min_sharpe: form.min_sharpe,
        min_sharpe_crypto: form.min_sharpe_crypto,
        min_sharpe_commodity: form.min_sharpe_commodity,
        min_win_rate: form.min_win_rate,
        min_win_rate_crypto: form.min_win_rate_crypto,
        min_win_rate_commodity: form.min_win_rate_commodity,
        min_trades_dsl: form.min_trades_dsl,
        min_trades_dsl_4h: form.min_trades_dsl_4h,
        min_trades_dsl_1h: form.min_trades_dsl_1h,
        min_trades_alpha_edge: form.min_trades_alpha_edge,
        min_trades_commodity: form.min_trades_commodity,
        disable_min_return_per_trade: form.disable_min_return_per_trade,
        disable_avg_loss_gate: form.disable_avg_loss_gate,
        grad_min_trades_1d: form.grad_min_trades_1d,
        grad_min_trades_4h: form.grad_min_trades_4h,
        grad_min_trades_1h: form.grad_min_trades_1h,
        grad_min_avg_pnl_per_trade: form.grad_min_avg_pnl_per_trade,
      })
      toast.success('Paper trading config saved')
    } catch (err) {
      toast.error(classifyError(err, 'save paper trading').message)
    }
  }

  return (
    <div className="max-w-[820px] space-y-4 pb-20">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Paper trading</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)] leading-[18px]">
          The DEMO pipeline exists for data collection, not profitability. These parameters are
          deliberately more permissive than live to maximise trade throughput and statistical
          coverage. The graduation gate is the quality filter — paper just needs enough trades
          to make a meaningful promotion decision.
        </p>
      </div>

      {/* Position sizing */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-medium text-[var(--text-0)]">Position sizing</h3>
          <InfoTip text="Flat fixed size per paper trade. Bypasses all vol/drawdown/conviction scaling — every strategy gets equal data quality. The $5K default always clears the eToro minimum and produces meaningful P&L data." />
        </div>
        <NumberRow
          label="Flat paper size"
          hint="Fixed $ per paper trade — no vol, drawdown, or conviction scaling"
          suffix="$"
          value={form?.flat_position_size ?? 5000}
          onChange={(v) => set('flat_position_size', v)}
          min={500}
          max={50000}
          step={500}
        />
      </Card>

      {/* Conviction thresholds */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-medium text-[var(--text-0)]">Paper conviction thresholds</h3>
          <InfoTip text="Lower than live to collect data on borderline strategies. The 60–64 band has real strategies with edge that need live data to resolve. Live thresholds are on the Live Trading tab." />
        </div>
        <NumberRow
          label="Equity threshold"
          hint="Paper conviction floor for equity — lower than live (73) to collect borderline data"
          value={form?.conviction_threshold ?? 60}
          onChange={(v) => set('conviction_threshold', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
        <NumberRow
          label="Crypto threshold"
          hint="Paper conviction floor for crypto"
          value={form?.conviction_threshold_crypto ?? 55}
          onChange={(v) => set('conviction_threshold_crypto', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
        <NumberRow
          label="Alpha Edge threshold"
          hint="Paper conviction floor for Alpha Edge (fundamental-path) strategies. Lower than equity because AE has a structural scoring ceiling (no carry/crypto components; WF-edge scored off a fundamental backtest). Mirrors the crypto offset."
          value={form?.conviction_threshold_alpha_edge ?? 55}
          onChange={(v) => set('conviction_threshold_alpha_edge', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
      </Card>

      {/* Activation thresholds */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-medium text-[var(--text-0)]">Activation thresholds (paper)</h3>
          <InfoTip text="These overlay the strict live activation thresholds for the paper pipeline only. WF Sharpe 0.5–1.0 is worth understanding — you need paper data to know if it holds live." />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <NumberRow
            label="Min Sharpe"
            hint="Default (was 1.0)"
            value={form?.min_sharpe ?? 0.5}
            onChange={(v) => set('min_sharpe', v)}
            min={-2}
            max={5}
            step={0.05}
          />
          <NumberRow
            label="Min Sharpe (crypto)"
            hint="Crypto (was 0.3)"
            value={form?.min_sharpe_crypto ?? 0.2}
            onChange={(v) => set('min_sharpe_crypto', v)}
            min={-2}
            max={5}
            step={0.05}
          />
          <NumberRow
            label="Min Sharpe (commodity)"
            hint="Commodity (was 0.5)"
            value={form?.min_sharpe_commodity ?? 0.3}
            onChange={(v) => set('min_sharpe_commodity', v)}
            min={-2}
            max={5}
            step={0.05}
          />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <NumberRow
            label="Min win rate"
            hint="Default % (was 45%)"
            suffix="%"
            value={form?.min_win_rate ?? 40}
            onChange={(v) => set('min_win_rate', v)}
            min={10}
            max={80}
            step={0.5}
          />
          <NumberRow
            label="Min WR (crypto)"
            hint="Crypto % (was 30%)"
            suffix="%"
            value={form?.min_win_rate_crypto ?? 25}
            onChange={(v) => set('min_win_rate_crypto', v)}
            min={10}
            max={80}
            step={0.5}
          />
          <NumberRow
            label="Min WR (commodity)"
            hint="Commodity % (was 35%)"
            suffix="%"
            value={form?.min_win_rate_commodity ?? 30}
            onChange={(v) => set('min_win_rate_commodity', v)}
            min={10}
            max={80}
            step={0.5}
          />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <NumberRow
            label="Min trades (DSL 1d)"
            hint="Daily DSL (was 8)"
            value={form?.min_trades_dsl ?? 5}
            onChange={(v) => set('min_trades_dsl', Math.round(v))}
            min={1}
            max={50}
            step={1}
          />
          <NumberRow
            label="Min trades (DSL 4h)"
            hint="4H DSL (was 8)"
            value={form?.min_trades_dsl_4h ?? 5}
            onChange={(v) => set('min_trades_dsl_4h', Math.round(v))}
            min={1}
            max={50}
            step={1}
          />
          <NumberRow
            label="Min trades (DSL 1h)"
            hint="1H DSL (was 12)"
            value={form?.min_trades_dsl_1h ?? 8}
            onChange={(v) => set('min_trades_dsl_1h', Math.round(v))}
            min={1}
            max={100}
            step={1}
          />
        </div>

        <div className="grid grid-cols-2 gap-2">
          <NumberRow
            label="Min trades (Alpha Edge)"
            hint="AE fundamental signals (was 6)"
            value={form?.min_trades_alpha_edge ?? 4}
            onChange={(v) => set('min_trades_alpha_edge', Math.round(v))}
            min={1}
            max={50}
            step={1}
          />
          <NumberRow
            label="Min trades (commodity)"
            hint="Commodity (was 6)"
            value={form?.min_trades_commodity ?? 4}
            onChange={(v) => set('min_trades_commodity', Math.round(v))}
            min={1}
            max={50}
            step={1}
          />
        </div>

        <div className="space-y-2 pt-1 border-t border-[var(--border-subtle)]">
          <ToggleRow
            label="Disable RPT gate"
            hint="Skip min-return-per-trade filter for paper activation. Recommended: ON — data collection, not profitability."
            checked={form?.disable_min_return_per_trade ?? true}
            onChange={(v) => set('disable_min_return_per_trade', v)}
          />
          <ToggleRow
            label="Disable avg-loss gate"
            hint="Skip expectancy/avg-loss filter for paper activation. Recommended: ON — need data on borderline strategies."
            checked={form?.disable_avg_loss_gate ?? true}
            onChange={(v) => set('disable_avg_loss_gate', v)}
          />
        </div>
      </Card>

      {/* Graduation gate */}
      <Card padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-medium text-[var(--text-0)]">Graduation gate (paper)</h3>
          <InfoTip text="Interval-aware min_trades: 1D strategies fire ~1/month, 4H ~2/month, 1H ~5/month. The trade count bar is a consistency check, not a significance test — the qualification ratio (paper Sharpe / WF Sharpe) is the real quality signal." />
        </div>
        <p className="text-[10px] text-[var(--text-3)] leading-[14px]">
          These override the global graduation_gate.min_trades for interval-specific decisions.
          Win rate (55%), qualification ratio (60–200% of WF Sharpe), and P&L {'>'} 0 are set on
          the Live Trading tab.
        </p>

        <div className="grid grid-cols-3 gap-2">
          <NumberRow
            label="Min trades (1D)"
            hint="~1 trade/month → 10 ≈ 10 months"
            value={form?.grad_min_trades_1d ?? 10}
            onChange={(v) => set('grad_min_trades_1d', Math.round(v))}
            min={3}
            max={100}
            step={1}
          />
          <NumberRow
            label="Min trades (4H)"
            hint="~2 trades/month → 15 ≈ 7 months"
            value={form?.grad_min_trades_4h ?? 15}
            onChange={(v) => set('grad_min_trades_4h', Math.round(v))}
            min={3}
            max={100}
            step={1}
          />
          <NumberRow
            label="Min trades (1H)"
            hint="~5 trades/month → 25 ≈ 5 months"
            value={form?.grad_min_trades_1h ?? 25}
            onChange={(v) => set('grad_min_trades_1h', Math.round(v))}
            min={5}
            max={200}
            step={1}
          />
        </div>

        <NumberRow
          label="Min avg P&L per trade"
          hint="Avg P&L per trade must exceed this. Prevents graduating strategies with technically positive total P&L but near-zero per-trade expectancy."
          suffix="$"
          value={form?.grad_min_avg_pnl_per_trade ?? 0}
          onChange={(v) => set('grad_min_avg_pnl_per_trade', v)}
          min={-1000}
          max={10000}
          step={1}
        />
      </Card>

      <SaveBar
        dirty={dirty}
        changeCount={changeCount}
        onSave={onSave}
        onReset={() => initial && setForm(initial)}
        loading={update.isPending}
      />
    </div>
  )
}

function extract(c: PaperTradingConfigShape) {
  return {
    flat_position_size: Number(c.flat_position_size ?? 5000),
    conviction_threshold: Number(c.conviction_threshold ?? 60),
    conviction_threshold_crypto: Number(c.conviction_threshold_crypto ?? 55),
    conviction_threshold_alpha_edge: Number(c.conviction_threshold_alpha_edge ?? 55),
    min_sharpe: Number(c.min_sharpe ?? 0.5),
    min_sharpe_crypto: Number(c.min_sharpe_crypto ?? 0.2),
    min_sharpe_commodity: Number(c.min_sharpe_commodity ?? 0.3),
    min_win_rate: Number(c.min_win_rate ?? 40),
    min_win_rate_crypto: Number(c.min_win_rate_crypto ?? 25),
    min_win_rate_commodity: Number(c.min_win_rate_commodity ?? 30),
    min_trades_dsl: Number(c.min_trades_dsl ?? 5),
    min_trades_dsl_4h: Number(c.min_trades_dsl_4h ?? 5),
    min_trades_dsl_1h: Number(c.min_trades_dsl_1h ?? 8),
    min_trades_alpha_edge: Number(c.min_trades_alpha_edge ?? 4),
    min_trades_commodity: Number(c.min_trades_commodity ?? 4),
    disable_min_return_per_trade: Boolean(c.disable_min_return_per_trade ?? true),
    disable_avg_loss_gate: Boolean(c.disable_avg_loss_gate ?? true),
    grad_min_trades_1d: Number(c.grad_min_trades_1d ?? 10),
    grad_min_trades_4h: Number(c.grad_min_trades_4h ?? 15),
    grad_min_trades_1h: Number(c.grad_min_trades_1h ?? 25),
    grad_min_avg_pnl_per_trade: Number(c.grad_min_avg_pnl_per_trade ?? 0),
  }
}

function InfoTip({ text }: { text: string }) {
  return (
    <span title={text} className="cursor-help text-[var(--text-3)] hover:text-[var(--text-1)]">
      <Info className="h-3 w-3" />
    </span>
  )
}

function NumberRow({
  label,
  hint,
  value,
  onChange,
  suffix,
  min,
  max,
  step,
}: {
  label: string
  hint: string
  value: number
  onChange: (v: number) => void
  suffix?: string
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div className="space-y-0.5">
      <Label className="text-[10px] text-[var(--text-2)]" title={hint}>
        {label}
      </Label>
      <div className="flex items-center gap-1">
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={min}
          max={max}
          step={step}
          className="h-7 mono tabular-nums text-right"
        />
        {suffix && <span className="text-[10px] text-[var(--text-3)] shrink-0">{suffix}</span>}
      </div>
      <div className="text-[9px] text-[var(--text-3)] leading-[12px]">{hint}</div>
    </div>
  )
}

function ToggleRow({
  label,
  hint,
  checked,
  onChange,
}: {
  label: string
  hint: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="flex-1 min-w-0">
        <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
        <div className="text-[10px] text-[var(--text-3)] leading-[14px] mt-0.5">{hint}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}
