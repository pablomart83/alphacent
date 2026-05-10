import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { ChevronDown, ChevronRight, Info, Search } from 'lucide-react'
import Fuse from 'fuse.js'
import {
  Button,
  Card,
  Input,
  Label,
  Switch,
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/primitives'
import { SaveBar, SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'
import { classifyError } from '@/lib/errors'
import {
  useAutonomousConfig,
  useUpdateAutonomousConfig,
} from '../useSettingsData'
import { AUTONOMOUS_FIELDS, AUTONOMOUS_SECTIONS, type FieldDef } from './autonomous-config-schema'

/**
 * Autonomous configuration form — the biggest and most dangerous form
 * in the product. ~80 fields organised by concern, each with an
 * info-tooltip that ties the value back to the log line or observable
 * it gates.
 *
 * Features:
 *   • Collapsible sections — default collapsed except the one containing
 *     the active search match (so searching auto-reveals the field).
 *   • In-form fuzzy search using Fuse over field label + help text.
 *   • SaveBar with change count + reset; PUT is idempotent on the whole
 *     payload, so partial updates are safe.
 */
export function AutonomousTab() {
  const config = useAutonomousConfig()
  const update = useUpdateAutonomousConfig()
  const initial = useMemo(
    () => (config.data ? pickEditableFields(config.data) : null),
    [config.data],
  )
  const [form, setForm] = useState<Record<string, unknown> | null>(null)
  const [query, setQuery] = useState('')
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})

  useEffect(() => {
    if (initial) setForm(initial)
  }, [initial])

  const fuse = useMemo(
    () =>
      new Fuse(AUTONOMOUS_FIELDS, {
        keys: ['label', 'help', 'section'],
        threshold: 0.35,
      }),
    [],
  )

  const matchingKeys = useMemo(() => {
    if (!query.trim()) return null
    const matches = fuse.search(query).map((r) => r.item.key)
    return new Set(matches)
  }, [query, fuse])

  const matchingSections = useMemo(() => {
    if (!matchingKeys) return new Set<string>()
    const set = new Set<string>()
    for (const f of AUTONOMOUS_FIELDS) {
      if (matchingKeys.has(f.key)) set.add(f.section)
    }
    return set
  }, [matchingKeys])

  const setField = (k: string, v: unknown) => {
    setForm((prev) => (prev ? { ...prev, [k]: v } : prev))
  }

  const dirty = !!form && !!initial && JSON.stringify(form) !== JSON.stringify(initial)
  const changeCount = useMemo(() => {
    if (!form || !initial) return 0
    let n = 0
    for (const k of Object.keys(form)) {
      if (JSON.stringify(form[k]) !== JSON.stringify(initial[k])) n += 1
    }
    return n
  }, [form, initial])

  const onSave = async () => {
    if (!form || !config.data) return
    try {
      // Merge form overrides onto the full server payload so we don't
      // drop read-only / advanced fields.
      await update.mutateAsync({ ...config.data, ...form })
      toast.success(`Autonomous config saved — ${changeCount} field${changeCount === 1 ? '' : 's'}`)
    } catch (err) {
      toast.error(classifyError(err, 'save autonomous config').message)
    }
  }

  const toggleSection = (s: string) => {
    setExpanded((prev) => ({ ...prev, [s]: !prev[s] }))
  }

  return (
    <TooltipProvider>
      <div className="max-w-[900px] space-y-3 pb-24">
        <div className="flex items-end justify-between gap-3">
          <div className="space-y-1">
            <SectionLabel className="mb-0">Autonomous configuration</SectionLabel>
            <p className="text-[12px] text-[var(--text-2)] max-w-[640px]">
              Every cycle parameter that drives the proposer, walk-forward, conviction scorer,
              retirement and adaptive risk loop. Hover any label for the observable it gates.
            </p>
          </div>
          <div className="relative w-[280px]">
            <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-[var(--text-3)]" />
            <Input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search fields…"
              className="h-7 pl-7 text-[11px]"
            />
          </div>
        </div>

        {AUTONOMOUS_SECTIONS.map((section) => {
          const fields = AUTONOMOUS_FIELDS.filter((f) => f.section === section)
          const visibleFields = matchingKeys
            ? fields.filter((f) => matchingKeys.has(f.key))
            : fields
          if (!visibleFields.length) return null
          const isOpen =
            expanded[section] ??
            (matchingKeys ? matchingSections.has(section) : section === 'Core')
          return (
            <Card key={section} padding="sm">
              <button
                type="button"
                onClick={() => toggleSection(section)}
                className="flex items-center justify-between w-full text-left"
                aria-expanded={isOpen}
              >
                <div className="flex items-center gap-1.5">
                  {isOpen ? (
                    <ChevronDown className="h-3.5 w-3.5 text-[var(--text-2)]" />
                  ) : (
                    <ChevronRight className="h-3.5 w-3.5 text-[var(--text-2)]" />
                  )}
                  <span className="text-[12px] font-medium text-[var(--text-0)]">{section}</span>
                </div>
                <span className="text-[10px] text-[var(--text-3)]">
                  {visibleFields.length} field{visibleFields.length === 1 ? '' : 's'}
                </span>
              </button>
              {isOpen && (
                <div className="mt-2 space-y-2 border-t border-[var(--border-subtle)] pt-2">
                  {visibleFields.map((f) => (
                    <FieldRow
                      key={f.key}
                      def={f}
                      value={form?.[f.key]}
                      onChange={(v) => setField(f.key, v)}
                      highlight={!!matchingKeys?.has(f.key)}
                    />
                  ))}
                </div>
              )}
            </Card>
          )
        })}

        {form && initial && (
          <div className="flex items-center justify-between text-[10px] text-[var(--text-3)]">
            <span>
              {AUTONOMOUS_FIELDS.length} editable fields · {changeCount} pending change
              {changeCount === 1 ? '' : 's'}
            </span>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setExpanded(Object.fromEntries(AUTONOMOUS_SECTIONS.map((s) => [s, true])))}
            >
              Expand all
            </Button>
          </div>
        )}

        <SaveBar
          dirty={dirty}
          changeCount={changeCount}
          onSave={onSave}
          onReset={() => initial && setForm(initial)}
          loading={update.isPending}
        />
      </div>
    </TooltipProvider>
  )
}

function FieldRow({
  def,
  value,
  onChange,
  highlight,
}: {
  def: FieldDef
  value: unknown
  onChange: (v: unknown) => void
  highlight?: boolean
}) {
  return (
    <div
      className={cn(
        'grid grid-cols-[260px_1fr_140px] items-center gap-3 px-2 py-1 rounded-[3px]',
        highlight && 'bg-[color-mix(in_oklab,var(--accent-primary)_6%,transparent)]',
      )}
    >
      <div className="flex items-center gap-1 min-w-0">
        <Label
          className="text-[11px] text-[var(--text-1)] truncate"
          title={def.label}
          htmlFor={def.key}
        >
          {def.label}
        </Label>
        {def.help && (
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="text-[var(--text-3)] hover:text-[var(--text-0)]"
                aria-label={`Info for ${def.label}`}
              >
                <Info className="h-3 w-3" />
              </button>
            </TooltipTrigger>
            <TooltipContent className="max-w-[260px] text-[10px] leading-[15px]">
              {def.help}
              {def.gates && (
                <div className="mt-1 pt-1 border-t border-[var(--border-subtle)] text-[var(--text-3)]">
                  Gates: <code className="mono">{def.gates}</code>
                </div>
              )}
            </TooltipContent>
          </Tooltip>
        )}
      </div>
      <div className="text-[10px] text-[var(--text-3)] truncate">{def.help}</div>
      <FieldInput def={def} value={value} onChange={onChange} />
    </div>
  )
}

function FieldInput({
  def,
  value,
  onChange,
}: {
  def: FieldDef
  value: unknown
  onChange: (v: unknown) => void
}) {
  if (def.type === 'bool') {
    return (
      <div className="flex justify-end">
        <Switch checked={Boolean(value)} onCheckedChange={(v) => onChange(v)} />
      </div>
    )
  }
  if (def.type === 'string') {
    return (
      <Input
        id={def.key}
        value={typeof value === 'string' ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        className="h-7 mono text-[11px] text-right"
      />
    )
  }
  return (
    <div className="flex items-center gap-1">
      <Input
        id={def.key}
        type="number"
        value={typeof value === 'number' ? value : value == null ? '' : Number(value)}
        onChange={(e) => onChange(e.target.value === '' ? null : Number(e.target.value))}
        step={def.step ?? (def.type === 'int' ? 1 : 0.01)}
        min={def.min}
        max={def.max}
        className="h-7 mono tabular-nums text-right"
      />
      {def.suffix && <span className="text-[10px] text-[var(--text-3)]">{def.suffix}</span>}
    </div>
  )
}

function pickEditableFields(
  full: Record<string, unknown>,
): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const f of AUTONOMOUS_FIELDS) {
    out[f.key] = full[f.key]
  }
  return out
}
