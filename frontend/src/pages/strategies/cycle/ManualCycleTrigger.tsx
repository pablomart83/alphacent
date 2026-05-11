import { useState } from 'react'
import { toast } from 'sonner'
import { PlayCircle } from 'lucide-react'
import { Button, ConfirmDialog } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { useTriggerCycle, type TriggerCycleBody } from '../useStrategiesData'

/**
 * ManualCycleTrigger — filter by asset class / interval and run a cycle now.
 * Backend accepts any subset; empty arrays = run full universe.
 */

const ASSET_CLASSES: Array<{ value: string; label: string }> = [
  { value: 'stock', label: 'Stocks' },
  { value: 'etf', label: 'ETFs' },
  { value: 'crypto', label: 'Crypto' },
  { value: 'forex', label: 'Forex' },
  { value: 'index', label: 'Indices' },
  { value: 'commodity', label: 'Commodities' },
]

const INTERVALS: Array<{ value: string; label: string }> = [
  { value: '1d', label: '1D' },
  { value: '4h', label: '4H' },
  { value: '1h', label: '1H' },
]

const STRATEGY_TYPES: Array<{ value: string; label: string }> = [
  { value: 'dsl', label: 'DSL' },
  { value: 'alpha_edge', label: 'Alpha Edge' },
]

const STORAGE_KEY = 'alphacent_cycle_trigger_prefs'

function loadPrefs() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { assetClasses: [], intervals: [], strategyTypes: [], force: false }
    return JSON.parse(raw)
  } catch {
    return { assetClasses: [], intervals: [], strategyTypes: [], force: false }
  }
}

function savePrefs(prefs: { assetClasses: string[]; intervals: string[]; strategyTypes: string[]; force: boolean }) {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs)) } catch {}
}

export function ManualCycleTrigger() {
  const mutation = useTriggerCycle()
  const [assetClasses, setAssetClasses] = useState<string[]>(() => loadPrefs().assetClasses)
  const [intervals, setIntervals] = useState<string[]>(() => loadPrefs().intervals)
  const [strategyTypes, setStrategyTypes] = useState<string[]>(() => loadPrefs().strategyTypes)
  const [force, setForce] = useState<boolean>(() => loadPrefs().force)
  const [confirmOpen, setConfirmOpen] = useState(false)

  const toggle = (list: string[], setter: (l: string[]) => void, value: string, key: 'assetClasses' | 'intervals' | 'strategyTypes') => {
    const next = list.includes(value) ? list.filter((v) => v !== value) : [...list, value]
    setter(next)
    savePrefs({
      assetClasses: key === 'assetClasses' ? next : assetClasses,
      intervals: key === 'intervals' ? next : intervals,
      strategyTypes: key === 'strategyTypes' ? next : strategyTypes,
      force,
    })
  }

  const handleConfirm = async () => {
    const body: TriggerCycleBody = { force }
    if (assetClasses.length) body.asset_classes = assetClasses
    if (intervals.length) body.intervals = intervals
    if (strategyTypes.length) body.strategy_types = strategyTypes

    try {
      const res = await mutation.mutateAsync(body)
      toast.success(res.message, {
        description: res.cycle_id ? `Cycle ID: ${res.cycle_id}` : undefined,
      })
    } catch (err) {
      notifyError(err, 'trigger cycle')
    } finally {
      setConfirmOpen(false)
    }
  }

  const hasFilters = assetClasses.length || intervals.length || strategyTypes.length

  return (
    <section className="flex flex-col gap-2 p-2">
      <SectionLabel>Run cycle now</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 flex flex-col gap-2">
        <ChipGroup
          label="Asset classes"
          options={ASSET_CLASSES}
          selected={assetClasses}
          onToggle={(v) => toggle(assetClasses, setAssetClasses, v, 'assetClasses')}
        />
        <ChipGroup
          label="Intervals"
          options={INTERVALS}
          selected={intervals}
          onToggle={(v) => toggle(intervals, setIntervals, v, 'intervals')}
        />
        <ChipGroup
          label="Strategy types"
          options={STRATEGY_TYPES}
          selected={strategyTypes}
          onToggle={(v) => toggle(strategyTypes, setStrategyTypes, v, 'strategyTypes')}
        />
        <label className="inline-flex items-center gap-1.5 text-[10px] text-[var(--text-2)] cursor-pointer">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => {
              setForce(e.target.checked)
              savePrefs({ assetClasses, intervals, strategyTypes, force: e.target.checked })
            }}
            className="h-3 w-3 accent-[var(--accent-primary)]"
          />
          Force — override disabled autonomous flag
        </label>
        <Button
          variant="primary"
          size="sm"
          onClick={() => setConfirmOpen(true)}
          loading={mutation.isPending}
          className="gap-1.5"
        >
          <PlayCircle className="h-3.5 w-3.5" />
          Run cycle now
        </Button>
        <div className="text-[10px] text-[var(--text-3)]">
          {hasFilters
            ? `Scoped to ${[
                assetClasses.length ? `${assetClasses.length} asset class${assetClasses.length === 1 ? '' : 'es'}` : null,
                intervals.length ? `${intervals.length} interval${intervals.length === 1 ? '' : 's'}` : null,
                strategyTypes.length ? `${strategyTypes.length} strategy type${strategyTypes.length === 1 ? '' : 's'}` : null,
              ]
                .filter(Boolean)
                .join(' · ')}`
            : 'No filters — runs the full universe.'}
        </div>
      </div>

      <ConfirmDialog
        open={confirmOpen}
        onOpenChange={setConfirmOpen}
        title="Run autonomous cycle now"
        description={confirmDescription({ force, assetClasses, intervals, strategyTypes })}
        confirmLabel="Run cycle"
        confirmVariant="primary"
        isLoading={mutation.isPending}
        onConfirm={handleConfirm}
      />
    </section>
  )
}

function ChipGroup({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string
  options: Array<{ value: string; label: string }>
  selected: string[]
  onToggle: (value: string) => void
}) {
  return (
    <div>
      <div className="text-[9px] uppercase tracking-wider text-[var(--text-3)] mb-1">{label}</div>
      <div className="flex flex-wrap gap-1">
        {options.map((o) => {
          const active = selected.includes(o.value)
          return (
            <button
              key={o.value}
              type="button"
              onClick={() => onToggle(o.value)}
              className={cn(
                'h-6 px-2 rounded-[2px] text-[10px] font-medium uppercase tracking-wide transition-colors',
                'border',
                active
                  ? 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)] text-[var(--accent-primary)] border-[var(--accent-primary)]/30'
                  : 'bg-[var(--bg-2)] text-[var(--text-2)] border-transparent hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
              )}
            >
              {o.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function confirmDescription(opts: {
  force: boolean
  assetClasses: string[]
  intervals: string[]
  strategyTypes: string[]
}): string {
  const parts: string[] = []
  if (opts.assetClasses.length) parts.push(`asset classes: ${opts.assetClasses.join(', ')}`)
  if (opts.intervals.length) parts.push(`intervals: ${opts.intervals.join(', ')}`)
  if (opts.strategyTypes.length) parts.push(`types: ${opts.strategyTypes.join(', ')}`)
  const filters = parts.length ? parts.join(' · ') : 'Full universe'
  const forcePrefix = opts.force ? 'Force mode — bypasses the disabled flag. ' : ''
  return `${forcePrefix}This runs the full 9-stage pipeline (cleanup → signals). Scope: ${filters}. Duration typically 5-10 min. Progress streams to the pipeline visual.`
}
