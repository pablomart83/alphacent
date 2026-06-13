import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { AlertTriangle, Info } from 'lucide-react'
import { Card, Input, Label, Switch } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  useLiveTradingConfig,
  useUpdateLiveTradingConfig,
  type LiveTradingConfigShape,
} from '../useSettingsData'

/**
 * Live Trading config — the guardrails around real money. Toggling
 * `enabled` off stops new live fills instantly; existing positions keep
 * running under their own stops.
 */
export function LiveTradingSettingsTab() {
  const cfg = useLiveTradingConfig()
  const update = useUpdateLiveTradingConfig()
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
        enabled: form.enabled,
        base_risk_pct: form.base_risk_pct / 100,
        min_order_size: form.min_order_size,
        max_order_size: form.max_order_size,
        symbol_cap: form.symbol_cap,
        mirror_ratio: form.mirror_ratio / 100,
        conviction_threshold: form.conviction_threshold,
        conviction_threshold_crypto: form.conviction_threshold_crypto,
        conviction_threshold_alpha_edge: form.conviction_threshold_alpha_edge,
        graduation_min_trades: form.graduation_min_trades,
        graduation_min_win_rate: form.graduation_min_win_rate,
        graduation_min_qualification_ratio: form.graduation_min_qualification_ratio,
        graduation_rejection_cooldown_days: form.graduation_rejection_cooldown_days,
      })
      toast.success('Live trading config saved')
    } catch (err) {
      toast.error(classifyError(err, 'save live trading').message)
    }
  }

  return (
    <div className="max-w-[820px] space-y-4 pb-20">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Live trading</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Controls the live Agent Portfolio — real money. The virtual balance is $10K; eToro mirrors
          at the ratio below to produce ~$1K real exposure. Conviction thresholds are independent
          from DEMO and intentionally tighter.
        </p>
      </div>

      {form?.enabled && (
        <div className="flex items-start gap-2 rounded-[3px] border border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_8%,var(--bg-1))] px-3 py-2 text-[11px]">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--status-warning)]" />
          <div>
            <div className="font-medium text-[var(--text-0)]">Live trading is ON</div>
            <div className="text-[var(--text-2)] mt-0.5">
              New approved signals will execute against the real eToro account. Disable here or via
              Guard → Kill Switch to stop fills immediately. Existing positions keep running.
            </div>
          </div>
        </div>
      )}

      <Card padding="md" className="space-y-3">
        <div className="flex items-center justify-between gap-3">
          <div>
            <Label className="text-[11px] text-[var(--text-1)]">Enabled</Label>
            <div className="text-[10px] text-[var(--text-3)]">
              Master switch — when off, all live signals are skipped at fill time.
            </div>
          </div>
          <Switch checked={form?.enabled ?? false} onCheckedChange={(v) => set('enabled', v)} />
        </div>
      </Card>

      <Card padding="md" className="space-y-3">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">Sizing</h3>
        <NumberRow
          label="Base risk %"
          hint="% of virtual equity risked per trade"
          suffix="%"
          value={form?.base_risk_pct ?? 0}
          onChange={(v) => set('base_risk_pct', v)}
          min={0}
          max={5}
          step={0.05}
        />
        <NumberRow
          label="Min order size"
          hint="Virtual dollars — eToro mirrors to real dollars via ratio"
          suffix="$"
          value={form?.min_order_size ?? 0}
          onChange={(v) => set('min_order_size', v)}
          min={0}
          max={5000}
          step={50}
        />
        <NumberRow
          label="Max order size"
          hint="Virtual dollars — hard ceiling per order"
          suffix="$"
          value={form?.max_order_size ?? 0}
          onChange={(v) => set('max_order_size', v)}
          min={0}
          max={20000}
          step={100}
        />
        <NumberRow
          label="Symbol cap"
          hint="Virtual dollars — hard ceiling on exposure per symbol"
          suffix="$"
          value={form?.symbol_cap ?? 0}
          onChange={(v) => set('symbol_cap', v)}
          min={0}
          max={30000}
          step={100}
        />
        <NumberRow
          label="Mirror ratio"
          hint="Real dollars per virtual dollar — ratio × virtual = real exposure"
          suffix="%"
          value={form?.mirror_ratio ?? 0}
          onChange={(v) => set('mirror_ratio', v)}
          min={0}
          max={100}
          step={0.5}
        />
      </Card>

      <Card padding="md" className="space-y-3">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">Live conviction thresholds</h3>
        <NumberRow
          label="Equity threshold"
          hint="Conviction floor for equity signals to fill live (DEMO equivalent is on Autonomous tab)"
          value={form?.conviction_threshold ?? 0}
          onChange={(v) => set('conviction_threshold', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
        <NumberRow
          label="Crypto threshold"
          hint="Conviction floor for crypto signals — typically lower than equity"
          value={form?.conviction_threshold_crypto ?? 0}
          onChange={(v) => set('conviction_threshold_crypto', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
        <NumberRow
          label="Alpha Edge threshold"
          hint="Conviction floor for live Alpha Edge (fundamental-path) signals. Per-pair CIO conviction_min still overrides at graduation; this is the default fallback."
          value={form?.conviction_threshold_alpha_edge ?? 0}
          onChange={(v) => set('conviction_threshold_alpha_edge', Math.round(v))}
          min={40}
          max={100}
          step={1}
        />
      </Card>

      <Card padding="md" className="space-y-3">
        <div className="flex items-center gap-2">
          <h3 className="text-[12px] font-medium text-[var(--text-0)]">Graduation gate thresholds</h3>
          <Info className="h-3.5 w-3.5 text-[var(--accent-primary)]" />
        </div>
        <p className="text-[10px] text-[var(--text-3)] leading-[14px]">
          A (template, symbol) pair must clear all four gates before appearing in the graduation
          queue. Changes take effect immediately — no restart needed.
        </p>
        <NumberRow
          label="Min paper trades"
          hint="Closed trades with P&L in trade_journal across all strategy versions for this pair"
          value={form?.graduation_min_trades ?? 20}
          onChange={(v) => set('graduation_min_trades', Math.round(v))}
          min={5}
          max={100}
          step={1}
        />
        <NumberRow
          label="Min win rate"
          hint="% of trades that must be profitable — 55% is the live-money floor"
          suffix="%"
          value={form?.graduation_min_win_rate ?? 55}
          onChange={(v) => set('graduation_min_win_rate', v)}
          min={30}
          max={90}
          step={1}
        />
        <NumberRow
          label="Min qualification ratio"
          hint="paper_sharpe / wf_sharpe — live performance must track walk-forward (0.60 = 60%)"
          value={form?.graduation_min_qualification_ratio ?? 0.60}
          onChange={(v) => set('graduation_min_qualification_ratio', v)}
          min={0.1}
          max={1.0}
          step={0.05}
        />
        <NumberRow
          label="Rejection cooldown"
          hint="Days before a rejected pair can re-appear in the queue"
          suffix="d"
          value={form?.graduation_rejection_cooldown_days ?? 14}
          onChange={(v) => set('graduation_rejection_cooldown_days', Math.round(v))}
          min={1}
          max={90}
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

function extract(c: LiveTradingConfigShape) {
  return {
    enabled: Boolean(c.enabled),
    base_risk_pct: Number(((c.base_risk_pct ?? 0) * 100).toFixed(2)),
    min_order_size: Number(c.min_order_size ?? 0),
    max_order_size: Number(c.max_order_size ?? 0),
    symbol_cap: Number(c.symbol_cap ?? 0),
    mirror_ratio: Number(((c.mirror_ratio ?? 0) * 100).toFixed(2)),
    conviction_threshold: Number(c.conviction_threshold ?? 0),
    conviction_threshold_crypto: Number(c.conviction_threshold_crypto ?? 0),
    conviction_threshold_alpha_edge: Number(c.conviction_threshold_alpha_edge ?? 67),
    graduation_min_trades: Number(c.graduation_min_trades ?? 20),
    graduation_min_win_rate: Number(c.graduation_min_win_rate ?? 55),
    graduation_min_qualification_ratio: Number(c.graduation_min_qualification_ratio ?? 0.60),
    graduation_rejection_cooldown_days: Number(c.graduation_rejection_cooldown_days ?? 14),
  }
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
    <div className="grid grid-cols-[180px_1fr_120px] items-center gap-3">
      <div>
        <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
      </div>
      <div className="text-[10px] text-[var(--text-3)]">{hint}</div>
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
        {suffix && <span className="text-[10px] text-[var(--text-3)]">{suffix}</span>}
      </div>
    </div>
  )
}

// (end of file)
