import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Card, Input, Label, Switch } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { useTradingMode } from '@/stores'
import {
  useRiskConfig,
  useUpdateRiskConfig,
  type RiskConfigShape,
} from '../useSettingsData'

/**
 * Position management — trailing-stop parameters, partial-exit levels,
 * stale-order cancellation, regime-based sizing.
 *
 * Lives alongside Risk Limits but isolated because these fields are more
 * about lifecycle than hard caps.
 */
export function PositionManagementTab() {
  const mode = useTradingMode((s) => s.mode)
  const config = useRiskConfig(mode)
  const update = useUpdateRiskConfig()

  const initial = useMemo(() => (config.data ? extract(config.data) : null), [config.data])
  const [form, setForm] = useState<typeof initial>(null)

  useEffect(() => {
    if (initial) setForm(initial)
  }, [initial])

  const dirty = useMemo(
    () => (initial && form ? JSON.stringify(initial) !== JSON.stringify(form) : false),
    [initial, form],
  )
  const changeCount = useMemo(() => {
    if (!initial || !form) return 0
    let n = 0
    for (const k of Object.keys(form) as Array<keyof typeof form>) {
      if (JSON.stringify(initial[k]) !== JSON.stringify(form[k])) n += 1
    }
    return n
  }, [initial, form])

  const setField = <K extends keyof Exclude<typeof form, null>>(
    k: K,
    v: Exclude<typeof form, null>[K],
  ) => {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev))
  }

  const onSave = async () => {
    if (!form || !config.data) return
    try {
      await update.mutateAsync({
        ...config.data,
        mode,
        trailing_stop_enabled: form.trailing_stop_enabled,
        trailing_stop_activation_pct: form.trailing_stop_activation_pct / 100,
        trailing_stop_distance_pct: form.trailing_stop_distance_pct / 100,
        partial_exit_enabled: form.partial_exit_enabled,
        correlation_adjustment_enabled: form.correlation_adjustment_enabled,
        correlation_threshold: form.correlation_threshold,
        correlation_reduction_factor: form.correlation_reduction_factor,
        regime_based_sizing_enabled: form.regime_based_sizing_enabled,
        cancel_stale_orders: form.cancel_stale_orders,
        stale_order_hours: form.stale_order_hours,
      })
      toast.success('Position management saved')
    } catch (err) {
      toast.error(classifyError(err, 'save position management').message)
    }
  }

  return (
    <div className="max-w-[820px] space-y-4 pb-20">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Position management · {mode}</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Lifecycle parameters — trailing stop ratchet, partial exits, correlation reduction,
          regime-based sizing, stale-order auto-cancel. Read the steering file for how each value
          interacts with the 60s monitoring loop.
        </p>
      </div>

      <Card padding="md" className="space-y-3">
        <ToggleRow
          label="Trailing stop"
          hint="Ratchets SL upward as price moves in favour. DB-side enforcement only for LIVE (eToro has no SL update API)."
          checked={form?.trailing_stop_enabled ?? false}
          onChange={(v) => setField('trailing_stop_enabled', v)}
        />
        <NumberRow
          label="TS activation"
          hint="Position must gain this % before trail activates"
          suffix="%"
          value={form?.trailing_stop_activation_pct ?? 0}
          onChange={(v) => setField('trailing_stop_activation_pct', v)}
          max={30}
          disabled={!form?.trailing_stop_enabled}
        />
        <NumberRow
          label="TS distance"
          hint="Trail distance below current price"
          suffix="%"
          value={form?.trailing_stop_distance_pct ?? 0}
          onChange={(v) => setField('trailing_stop_distance_pct', v)}
          max={20}
          disabled={!form?.trailing_stop_enabled}
        />
      </Card>

      <Card padding="md" className="space-y-3">
        <ToggleRow
          label="Partial exits"
          hint="Multi-level exit ladder — levels configured in autonomous_trading.yaml directly"
          checked={form?.partial_exit_enabled ?? false}
          onChange={(v) => setField('partial_exit_enabled', v)}
        />
        <ToggleRow
          label="Correlation adjustment"
          hint="Downsize positions that are highly correlated to existing exposures"
          checked={form?.correlation_adjustment_enabled ?? false}
          onChange={(v) => setField('correlation_adjustment_enabled', v)}
        />
        <NumberRow
          label="Correlation threshold"
          hint="|ρ| above this triggers the reduction factor"
          value={(form?.correlation_threshold ?? 0) * 100}
          onChange={(v) => setField('correlation_threshold', v / 100)}
          max={100}
          suffix="%"
          disabled={!form?.correlation_adjustment_enabled}
        />
        <NumberRow
          label="Reduction factor"
          hint="Downsize new positions by this fraction when correlated"
          value={(form?.correlation_reduction_factor ?? 0) * 100}
          onChange={(v) => setField('correlation_reduction_factor', v / 100)}
          max={100}
          suffix="%"
          disabled={!form?.correlation_adjustment_enabled}
        />
      </Card>

      <Card padding="md" className="space-y-3">
        <ToggleRow
          label="Regime-based sizing"
          hint="Scale position sizes by regime multipliers defined in autonomous_trading.yaml"
          checked={form?.regime_based_sizing_enabled ?? false}
          onChange={(v) => setField('regime_based_sizing_enabled', v)}
        />
        <ToggleRow
          label="Cancel stale orders"
          hint="Auto-cancel PENDING orders older than the threshold below"
          checked={form?.cancel_stale_orders ?? false}
          onChange={(v) => setField('cancel_stale_orders', v)}
        />
        <NumberRow
          label="Stale order age"
          hint="Hours before a pending order is auto-cancelled"
          suffix="h"
          value={form?.stale_order_hours ?? 0}
          onChange={(v) => setField('stale_order_hours', Math.round(v))}
          max={168}
          disabled={!form?.cancel_stale_orders}
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

function extract(c: RiskConfigShape) {
  return {
    trailing_stop_enabled: c.trailing_stop_enabled ?? false,
    trailing_stop_activation_pct: Number(((c.trailing_stop_activation_pct ?? 0) * 100).toFixed(2)),
    trailing_stop_distance_pct: Number(((c.trailing_stop_distance_pct ?? 0) * 100).toFixed(2)),
    partial_exit_enabled: c.partial_exit_enabled ?? false,
    correlation_adjustment_enabled: c.correlation_adjustment_enabled ?? false,
    correlation_threshold: c.correlation_threshold ?? 0.7,
    correlation_reduction_factor: c.correlation_reduction_factor ?? 0.5,
    regime_based_sizing_enabled: c.regime_based_sizing_enabled ?? false,
    cancel_stale_orders: c.cancel_stale_orders ?? false,
    stale_order_hours: c.stale_order_hours ?? 24,
  }
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
    <div className="flex items-center justify-between gap-3">
      <div className="min-w-0">
        <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
        <div className="text-[10px] text-[var(--text-3)]">{hint}</div>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

function NumberRow({
  label,
  hint,
  value,
  onChange,
  suffix,
  max = 100,
  disabled,
}: {
  label: string
  hint: string
  value: number
  onChange: (v: number) => void
  suffix?: string
  max?: number
  disabled?: boolean
}) {
  return (
    <div className="grid grid-cols-[200px_1fr_120px] items-center gap-3">
      <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
      <div className="text-[10px] text-[var(--text-3)]">{hint}</div>
      <div className="flex items-center gap-1">
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={0}
          max={max}
          step={0.1}
          className="h-7 mono tabular-nums text-right"
          disabled={disabled}
        />
        {suffix && <span className="text-[10px] text-[var(--text-3)]">{suffix}</span>}
      </div>
    </div>
  )
}
