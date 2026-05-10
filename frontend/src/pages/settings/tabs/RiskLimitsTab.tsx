import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Card, Input, Label } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { useTradingMode } from '@/stores'
import { useRiskConfig, useUpdateRiskConfig } from '../useSettingsData'

/**
 * Risk limits — per-mode dollar / % caps. Numbers are stored as decimal
 * fractions server-side (0.05 = 5%) so the form converts on both edges.
 */
export function RiskLimitsTab() {
  const mode = useTradingMode((s) => s.mode)
  const config = useRiskConfig(mode)
  const update = useUpdateRiskConfig()

  const initial = useMemo(() => {
    if (!config.data) return null
    return {
      max_position_size_pct: pct(config.data.max_position_size_pct),
      max_exposure_pct: pct(config.data.max_exposure_pct),
      max_daily_loss_pct: pct(config.data.max_daily_loss_pct),
      max_drawdown_pct: pct(config.data.max_drawdown_pct),
      position_risk_pct: pct(config.data.position_risk_pct),
      stop_loss_pct: pct(config.data.stop_loss_pct),
      take_profit_pct: pct(config.data.take_profit_pct),
    }
  }, [config.data])

  const [form, setForm] = useState<typeof initial>(null)

  useEffect(() => {
    if (initial) setForm(initial)
  }, [initial])

  const dirty = useMemo(() => {
    if (!initial || !form) return false
    return JSON.stringify(initial) !== JSON.stringify(form)
  }, [initial, form])

  const changeCount = useMemo(() => {
    if (!initial || !form) return 0
    let n = 0
    for (const k of Object.keys(form) as Array<keyof typeof form>) {
      if (initial[k] !== form[k]) n += 1
    }
    return n
  }, [initial, form])

  const setField = (k: keyof Exclude<typeof form, null>, v: number) => {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev))
  }

  const onSave = async () => {
    if (!form || !config.data) return
    try {
      await update.mutateAsync({
        ...config.data,
        mode,
        max_position_size_pct: form.max_position_size_pct / 100,
        max_exposure_pct: form.max_exposure_pct / 100,
        max_daily_loss_pct: form.max_daily_loss_pct / 100,
        max_drawdown_pct: form.max_drawdown_pct / 100,
        position_risk_pct: form.position_risk_pct / 100,
        stop_loss_pct: form.stop_loss_pct / 100,
        take_profit_pct: form.take_profit_pct / 100,
      })
      toast.success('Risk limits saved')
    } catch (err) {
      toast.error(classifyError(err, 'save risk limits').message)
    }
  }

  const onReset = () => {
    if (initial) setForm(initial)
  }

  const fields: Array<{ key: keyof Exclude<typeof form, null>; label: string; hint: string; max?: number }> = [
    { key: 'max_position_size_pct', label: 'Max position size', hint: '% of equity per single position', max: 25 },
    { key: 'max_exposure_pct', label: 'Max exposure', hint: 'Total open exposure as % of equity', max: 100 },
    { key: 'max_daily_loss_pct', label: 'Max daily loss', hint: '% equity drop triggering kill switch' },
    { key: 'max_drawdown_pct', label: 'Max drawdown', hint: '% peak-to-trough limit' },
    { key: 'position_risk_pct', label: 'Position risk', hint: '% of equity risked per trade', max: 5 },
    { key: 'stop_loss_pct', label: 'Default SL', hint: '% distance from entry — used when strategy sets no custom SL' },
    { key: 'take_profit_pct', label: 'Default TP', hint: '% distance from entry — used when strategy sets no custom TP' },
  ]

  return (
    <div className="max-w-[820px] space-y-4 pb-20">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Risk limits · {mode}</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Per-mode caps. Changes write to <code className="mono text-[10px]">config/risk_config.json</code> and
          take effect on the next risk validation cycle. The Guard surface's LimitEditor is a real-time
          subset of these settings — use this form for defaults that should survive restarts.
        </p>
      </div>
      <Card padding="md" className="space-y-2.5">
        {fields.map((f) => (
          <FieldRow
            key={f.key}
            label={f.label}
            hint={f.hint}
            value={form?.[f.key] ?? 0}
            onChange={(v) => setField(f.key, v)}
            max={f.max}
            loading={!form}
          />
        ))}
      </Card>
      <SaveBar
        dirty={dirty}
        changeCount={changeCount}
        onSave={onSave}
        onReset={onReset}
        loading={update.isPending}
      />
    </div>
  )
}

function FieldRow({
  label,
  hint,
  value,
  onChange,
  max = 100,
  loading,
}: {
  label: string
  hint: string
  value: number
  onChange: (v: number) => void
  max?: number
  loading?: boolean
}) {
  return (
    <div className="grid grid-cols-[200px_1fr_100px] items-center gap-3">
      <Label className="text-[11px] text-[var(--text-1)] truncate" title={label}>
        {label}
      </Label>
      <div>
        <input
          type="range"
          min={0}
          max={max}
          step={0.1}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          disabled={loading}
          className="w-full accent-[var(--accent-primary)]"
        />
        <div className="text-[10px] text-[var(--text-3)] mt-0.5">{hint}</div>
      </div>
      <div className="flex items-center gap-1">
        <Input
          type="number"
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          min={0}
          max={max}
          step={0.01}
          className="h-7 mono tabular-nums text-right"
          disabled={loading}
        />
        <span className="text-[10px] text-[var(--text-3)]">%</span>
      </div>
    </div>
  )
}

function pct(v: number | null | undefined): number {
  return v == null ? 0 : Number((v * 100).toFixed(2))
}
