import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Card, Input, Label, Switch } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  useAlphaEdgeConfig,
  useApiUsage,
  useUpdateAlphaEdgeConfig,
} from '../useSettingsData'

/**
 * Alpha Edge settings — fundamental filter toggles, ML filter, API-quota
 * telemetry from /config/alpha-edge/api-usage.
 */
export function AlphaEdgeSettingsTab() {
  const config = useAlphaEdgeConfig()
  const usage = useApiUsage()
  const update = useUpdateAlphaEdgeConfig()

  const initial = useMemo(() => (config.data ? { ...config.data } : null), [config.data])
  const [form, setForm] = useState<Record<string, unknown> | null>(null)

  useEffect(() => {
    if (initial) setForm(initial)
  }, [initial])

  const dirty = !!initial && !!form && JSON.stringify(initial) !== JSON.stringify(form)

  const toggle = (k: string, v: boolean) => setForm((p) => (p ? { ...p, [k]: v } : p))
  const setNum = (k: string, v: number) => setForm((p) => (p ? { ...p, [k]: v } : p))

  const onSave = async () => {
    if (!form) return
    try {
      await update.mutateAsync(form)
      toast.success('Alpha Edge settings saved')
    } catch (err) {
      toast.error(classifyError(err, 'save alpha edge').message)
    }
  }

  const fundamentalChecks: Array<{ key: string; label: string }> = [
    { key: 'check_profitable', label: 'Profitable' },
    { key: 'check_growing', label: 'Growing' },
    { key: 'check_reasonable_valuation', label: 'Reasonable valuation' },
    { key: 'check_no_dilution', label: 'No dilution' },
    { key: 'check_insider_buying', label: 'Insider buying' },
  ]

  return (
    <div className="max-w-[820px] space-y-4 pb-20">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Alpha Edge</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Toggle the fundamental and ML signal filters used by Alpha Edge templates. Thresholds are
          tuned here; per-template behaviour is in the Cycle tab under Templates.
        </p>
      </div>

      <Card padding="md" className="space-y-3">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">Fundamental filter</h3>
        <ToggleRow
          label="Filter enabled"
          checked={Boolean(form?.fundamental_filter_enabled)}
          onChange={(v) => toggle('fundamental_filter_enabled', v)}
        />
        <div className="grid grid-cols-2 gap-2">
          {fundamentalChecks.map((c) => (
            <ToggleRow
              key={c.key}
              label={c.label}
              checked={Boolean(form?.[c.key])}
              onChange={(v) => toggle(c.key, v)}
            />
          ))}
        </div>
      </Card>

      <Card padding="md" className="space-y-3">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">ML filter</h3>
        <ToggleRow
          label="ML filter enabled"
          checked={Boolean(form?.ml_filter_enabled)}
          onChange={(v) => toggle('ml_filter_enabled', v)}
        />
        <NumberRow
          label="Min confidence"
          suffix=""
          value={typeof form?.ml_min_confidence === 'number' ? (form.ml_min_confidence as number) : 0.5}
          onChange={(v) => setNum('ml_min_confidence', v)}
          min={0}
          max={1}
          step={0.01}
        />
        <NumberRow
          label="Retrain frequency"
          suffix="d"
          value={typeof form?.ml_retrain_days === 'number' ? (form.ml_retrain_days as number) : 7}
          onChange={(v) => setNum('ml_retrain_days', Math.round(v))}
          min={1}
          max={90}
          step={1}
        />
      </Card>

      <Card padding="md" className="space-y-2">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">API usage</h3>
        <p className="text-[11px] text-[var(--text-2)]">Polled from /config/alpha-edge/api-usage.</p>
        {usage.isLoading ? (
          <div className="h-[60px] animate-pulse bg-[var(--bg-2)] rounded-[3px]" />
        ) : (
          <pre className="text-[10px] mono text-[var(--text-2)] overflow-auto max-h-[200px] rounded-[3px] bg-[var(--bg-2)] px-2 py-1.5">
            {JSON.stringify(usage.data ?? {}, null, 2)}
          </pre>
        )}
      </Card>

      <SaveBar
        dirty={dirty}
        onSave={onSave}
        onReset={() => initial && setForm(initial)}
        loading={update.isPending}
      />
    </div>
  )
}

function ToggleRow({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
      <Switch checked={checked} onCheckedChange={onChange} />
    </div>
  )
}

function NumberRow({
  label,
  value,
  onChange,
  suffix,
  min,
  max,
  step,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  suffix?: string
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div className="grid grid-cols-[200px_1fr_120px] items-center gap-3">
      <Label className="text-[11px] text-[var(--text-1)]">{label}</Label>
      <div />
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
