import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { AlertTriangle } from 'lucide-react'
import { Label, Input, Skeleton } from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { useTradingMode } from '@/stores'
import {
  useUpdateRiskLimits,
  type RiskLimitsPayload,
  type RiskMetricsPayload,
  type UpdateRiskLimitsBody,
} from './useGuardData'

interface LimitEditorProps {
  limits: RiskLimitsPayload | null | undefined
  metrics: RiskMetricsPayload | null | undefined
  loading?: boolean
}

type FieldKey = keyof RiskLimitsPayload

interface FieldDef {
  key: FieldKey
  label: string
  unit: 'pct' | 'x'
  min: number
  max: number
  step: number
  /** Function returning the current metric value that should not exceed the new limit. */
  currentValue?: (m: RiskMetricsPayload) => number
  /** Label for the breach warning — "current drawdown is 7.2%". */
  currentLabel?: string
}

const FIELDS: FieldDef[] = [
  {
    key: 'max_position_size',
    label: 'Max position size',
    unit: 'pct',
    min: 0.5,
    max: 30,
    step: 0.5,
    currentValue: (m) => m.max_position_size,
    currentLabel: 'Largest position',
  },
  {
    key: 'max_portfolio_exposure',
    label: 'Max portfolio exposure',
    unit: 'pct',
    min: 10,
    max: 100,
    step: 1,
    currentValue: (m) => m.total_exposure,
    currentLabel: 'Total exposure',
  },
  {
    key: 'max_daily_loss',
    label: 'Max daily loss',
    unit: 'pct',
    min: 0.5,
    max: 20,
    step: 0.5,
  },
  {
    key: 'max_drawdown',
    label: 'Max drawdown',
    unit: 'pct',
    min: 5,
    max: 50,
    step: 1,
    currentValue: (m) => m.current_drawdown,
    currentLabel: 'Current drawdown',
  },
  {
    key: 'max_leverage',
    label: 'Max leverage',
    unit: 'x',
    min: 1,
    max: 10,
    step: 0.5,
    currentValue: (m) => m.leverage,
    currentLabel: 'Current leverage',
  },
  {
    key: 'risk_per_trade',
    label: 'Risk per trade',
    unit: 'pct',
    min: 0.1,
    max: 5,
    step: 0.1,
  },
]

export function LimitEditor({ limits, metrics, loading }: LimitEditorProps) {
  const mode = useTradingMode((s) => s.mode)
  const update = useUpdateRiskLimits()

  const [draft, setDraft] = useState<RiskLimitsPayload | null>(null)

  // Reset draft only when the backend values actually change — not on every
  // refetch that returns a new object reference with identical values.
  // This prevents in-progress edits from being silently discarded every 60s.
  useEffect(() => {
    if (!limits) return
    setDraft((prev) => {
      if (!prev) return limits
      // Check whether any field value has changed. If not, keep the existing
      // draft so the user's in-progress edits are preserved.
      const changed = (Object.keys(limits) as FieldKey[]).some(
        (k) => Math.abs((limits[k] as number) - (prev[k] as number)) > 1e-9,
      )
      return changed ? limits : prev
    })
  }, [limits])

  const changes = useMemo(() => {
    if (!draft || !limits) return [] as Array<{ key: FieldKey; from: number; to: number }>
    return FIELDS.map((f) => ({
      key: f.key,
      from: limits[f.key] as number,
      to: draft[f.key] as number,
    })).filter((c) => Math.abs(c.from - c.to) > 1e-9)
  }, [draft, limits])

  const dirty = changes.length > 0

  /* Warn when a proposed limit would be breached by current state. */
  const breachWarnings = useMemo(() => {
    if (!draft || !metrics) return []
    const warnings: string[] = []
    for (const f of FIELDS) {
      if (!f.currentValue) continue
      const newLimit = draft[f.key] as number
      const cur = f.currentValue(metrics)
      if (Number.isFinite(cur) && Number.isFinite(newLimit) && cur > newLimit) {
        const fmt = (v: number) => (f.unit === 'x' ? `${v.toFixed(2)}×` : `${v.toFixed(1)}%`)
        warnings.push(
          `${f.currentLabel ?? f.label} is ${fmt(cur)} — already above proposed ${f.label.toLowerCase()} of ${fmt(newLimit)}.`,
        )
      }
    }
    return warnings
  }, [draft, metrics])

  const setField = (key: FieldKey, value: number) => {
    if (!draft) return
    setDraft({ ...draft, [key]: value })
  }

  const handleReset = () => {
    if (limits) setDraft(limits)
  }

  const handleSave = async () => {
    if (!draft) return
    const body: UpdateRiskLimitsBody = {}
    for (const c of changes) body[c.key] = draft[c.key] as number
    try {
      await update.mutateAsync({ mode, body })
      toast.success(`Risk limits updated — ${changes.length} change${changes.length === 1 ? '' : 's'}`)
    } catch (err) {
      notifyError(err, 'update risk limits')
    }
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Limits · {mode}</SectionLabel>
      {loading && !draft ? (
        <div className="space-y-1.5">
          {FIELDS.map((f) => (
            <Skeleton key={f.key} className="h-8 w-full" />
          ))}
        </div>
      ) : draft ? (
        <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-2">
          {FIELDS.map((f) => (
            <Row
              key={f.key}
              field={f}
              value={draft[f.key] as number}
              original={(limits as RiskLimitsPayload)[f.key] as number}
              onChange={(v) => setField(f.key, v)}
            />
          ))}
          {breachWarnings.length > 0 && (
            <div className="rounded-[3px] border border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_10%,transparent)] p-2 space-y-1">
              <div className="flex items-center gap-1 text-[10px] font-medium text-[var(--status-warning)] uppercase tracking-wider">
                <AlertTriangle className="h-3 w-3" />
                Saving will put you above these limits
              </div>
              <ul className="space-y-0.5 text-[10px] text-[var(--text-1)]">
                {breachWarnings.map((w, i) => (
                  <li key={i}>· {w}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      ) : null}
      <SaveBar
        dirty={dirty}
        changeCount={changes.length}
        onSave={handleSave}
        onReset={handleReset}
        loading={update.isPending}
      />
    </section>
  )
}

function Row({
  field,
  value,
  original,
  onChange,
}: {
  field: FieldDef
  value: number
  original: number
  onChange: (v: number) => void
}) {
  const changed = Math.abs(value - original) > 1e-9
  const suffix = field.unit === 'x' ? '×' : '%'
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
          {field.label}
        </Label>
        <div className="flex items-baseline gap-1.5">
          {changed && (
            <span className="mono tabular-nums text-[10px] text-[var(--text-3)] line-through">
              {original.toFixed(field.step < 1 ? 1 : 0)}
              {suffix}
            </span>
          )}
          <div className="relative">
            <Input
              type="number"
              value={value}
              onChange={(e) => onChange(Number(e.target.value))}
              min={field.min}
              max={field.max}
              step={field.step}
              className={cn(
                'h-6 w-[80px] mono tabular-nums pr-5 text-[11px] text-right',
                changed && 'border-[var(--accent-primary)]',
              )}
            />
            <span className="absolute right-1.5 top-1/2 -translate-y-1/2 text-[9px] text-[var(--text-3)] pointer-events-none">
              {suffix}
            </span>
          </div>
        </div>
      </div>
      <input
        type="range"
        min={field.min}
        max={field.max}
        step={field.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--accent-primary)] mt-0.5"
      />
    </div>
  )
}
