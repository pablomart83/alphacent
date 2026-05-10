import { useEffect, useMemo, useState } from 'react'
import { toast } from 'sonner'
import { Plus, Trash2 } from 'lucide-react'
import {
  Button,
  Label,
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
  Skeleton,
  Switch,
} from '@/components/primitives'
import { SectionLabel, SaveBar } from '@/components/layout'
import { notifyError } from '@/lib/errors'
import { cn, formatTimestamp, parseUtcIso } from '@/lib/utils'
import {
  useAutonomousSchedules,
  useUpdateSchedules,
  type ScheduleSlot,
} from '../useStrategiesData'

/**
 * SchedulerPanel — multi-slot editor for the autonomous cycle schedule.
 * Each slot fires on selected days at the given UTC hour/minute.
 */

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const
const DAY_ABBR: Record<string, string> = {
  monday: 'M',
  tuesday: 'T',
  wednesday: 'W',
  thursday: 'T',
  friday: 'F',
  saturday: 'S',
  sunday: 'S',
}
const HOURS = Array.from({ length: 24 }, (_, i) => i)
const MINUTES = [0, 15, 30, 45]

function makeSlotId(): string {
  return `slot_${Math.random().toString(36).slice(2, 10)}`
}

function newSlot(): ScheduleSlot {
  return {
    id: makeSlotId(),
    enabled: true,
    days: ['monday', 'tuesday', 'wednesday', 'thursday', 'friday'],
    hour: 13,
    minute: 0,
  }
}

function slotsEqual(a: ScheduleSlot, b: ScheduleSlot): boolean {
  return (
    a.id === b.id &&
    a.enabled === b.enabled &&
    a.hour === b.hour &&
    a.minute === b.minute &&
    a.days.length === b.days.length &&
    a.days.every((d) => b.days.includes(d))
  )
}

function listsEqual(a: ScheduleSlot[], b: ScheduleSlot[]): boolean {
  if (a.length !== b.length) return false
  return a.every((slot, i) => slotsEqual(slot, b[i]))
}

function computeChangeCount(draft: ScheduleSlot[], server: ScheduleSlot[]): number {
  const draftIds = new Set(draft.map((s) => s.id))
  const serverIds = new Set(server.map((s) => s.id))
  let count = 0
  // Added + removed
  draftIds.forEach((id) => {
    if (!serverIds.has(id)) count++
  })
  serverIds.forEach((id) => {
    if (!draftIds.has(id)) count++
  })
  // Modified
  draft.forEach((s) => {
    const orig = server.find((x) => x.id === s.id)
    if (orig && !slotsEqual(s, orig)) count++
  })
  return count
}

export function SchedulerPanel() {
  const query = useAutonomousSchedules()
  const mutation = useUpdateSchedules()

  const serverSlots = query.data?.schedules ?? []
  const nextRuns = query.data?.next_runs ?? []

  const [draft, setDraft] = useState<ScheduleSlot[]>([])

  // Hydrate draft when the server state arrives / changes and we don't have
  // pending edits; once dirty, do not overwrite the user's work.
  useEffect(() => {
    if (query.isLoading) return
    setDraft((prev) => {
      if (prev.length === 0) return serverSlots
      return listsEqual(prev, serverSlots) ? serverSlots : prev
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serverSlots.length, query.isLoading])

  const isDirty = useMemo(() => !listsEqual(draft, serverSlots), [draft, serverSlots])

  const addSlot = () => setDraft((d) => [...d, newSlot()])
  const removeSlot = (id: string) => setDraft((d) => d.filter((s) => s.id !== id))
  const updateSlot = (id: string, patch: Partial<ScheduleSlot>) =>
    setDraft((d) => d.map((s) => (s.id === id ? { ...s, ...patch } : s)))
  const toggleDay = (id: string, day: string) =>
    setDraft((d) =>
      d.map((s) =>
        s.id === id
          ? {
              ...s,
              days: s.days.includes(day)
                ? s.days.filter((x) => x !== day)
                : [...s.days, day],
            }
          : s,
      ),
    )

  const handleSave = async () => {
    try {
      const res = await mutation.mutateAsync(draft)
      toast.success(res.message || 'Schedules saved')
    } catch (err) {
      notifyError(err, 'save schedules')
    }
  }

  const handleDiscard = () => setDraft(serverSlots)

  return (
    <section className="flex flex-col gap-2 p-2">
      <div className="flex items-center gap-2">
        <SectionLabel>Schedule</SectionLabel>
        <Button
          variant="ghost"
          size="sm"
          onClick={addSlot}
          className="ml-auto gap-1"
          title="Add a new schedule slot"
        >
          <Plus className="h-3 w-3" />
          Add slot
        </Button>
      </div>

      {query.isLoading ? (
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-16 w-full" />
          <Skeleton className="h-16 w-full" />
        </div>
      ) : draft.length === 0 ? (
        <div className="rounded-[3px] border border-dashed border-[var(--border-subtle)] bg-[var(--bg-1)] p-3 text-center">
          <div className="text-[11px] text-[var(--text-2)] mb-1.5">
            No schedule slots configured
          </div>
          <div className="text-[10px] text-[var(--text-3)] mb-2">
            The autonomous cycle will only run when manually triggered.
          </div>
          <Button variant="secondary" size="sm" onClick={addSlot}>
            Add your first slot
          </Button>
        </div>
      ) : (
        <div className="flex flex-col gap-1.5">
          {draft.map((slot, idx) => (
            <SlotCard
              key={slot.id}
              slot={slot}
              nextRun={nextRuns[idx] ?? null}
              onToggle={(enabled) => updateSlot(slot.id, { enabled })}
              onToggleDay={(d) => toggleDay(slot.id, d)}
              onHour={(h) => updateSlot(slot.id, { hour: h })}
              onMinute={(m) => updateSlot(slot.id, { minute: m })}
              onRemove={() => removeSlot(slot.id)}
            />
          ))}
        </div>
      )}

      <SaveBar
        dirty={isDirty}
        loading={mutation.isPending}
        onSave={handleSave}
        onReset={handleDiscard}
        changeCount={computeChangeCount(draft, serverSlots)}
      />
    </section>
  )
}

interface SlotCardProps {
  slot: ScheduleSlot
  nextRun: string | null
  onToggle: (enabled: boolean) => void
  onToggleDay: (day: string) => void
  onHour: (h: number) => void
  onMinute: (m: number) => void
  onRemove: () => void
}

function SlotCard({ slot, nextRun, onToggle, onToggleDay, onHour, onMinute, onRemove }: SlotCardProps) {
  const nextRunDate = nextRun ? parseUtcIso(nextRun) : null
  const nextRunLabel = nextRunDate && !Number.isNaN(nextRunDate.getTime())
    ? formatTimestamp(nextRunDate, 'short')
    : null

  return (
    <div
      className={cn(
        'rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2',
        !slot.enabled && 'opacity-60',
      )}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Switch
          checked={slot.enabled}
          onCheckedChange={onToggle}
          size="sm"
          aria-label="Enable slot"
        />
        <span className="text-[11px] font-medium text-[var(--text-0)]">
          {slot.enabled ? 'Enabled' : 'Disabled'}
        </span>
        <button
          type="button"
          onClick={onRemove}
          className="ml-auto h-5 w-5 inline-flex items-center justify-center rounded-[2px] text-[var(--text-3)] hover:text-[var(--pnl-down)] hover:bg-[var(--bg-hover)]"
          aria-label="Remove slot"
        >
          <Trash2 className="h-3 w-3" />
        </button>
      </div>

      <div className="flex items-center gap-0.5 mb-1.5">
        {DAYS.map((d) => {
          const active = slot.days.includes(d)
          return (
            <button
              key={d}
              type="button"
              onClick={() => onToggleDay(d)}
              title={d.charAt(0).toUpperCase() + d.slice(1)}
              className={cn(
                'h-6 w-6 rounded-[2px] text-[10px] font-semibold uppercase transition-colors',
                active
                  ? 'bg-[var(--accent-primary)] text-white'
                  : 'bg-[var(--bg-2)] text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
              )}
            >
              {DAY_ABBR[d]}
            </button>
          )
        })}
      </div>

      <div className="flex items-center gap-2">
        <Label className="text-[10px] text-[var(--text-3)] uppercase tracking-wide">UTC</Label>
        <Select value={String(slot.hour)} onValueChange={(v) => onHour(Number(v))}>
          <SelectTrigger size="sm" className="h-7 w-[70px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {HOURS.map((h) => (
              <SelectItem key={h} value={String(h)}>
                {String(h).padStart(2, '0')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className="text-[11px] text-[var(--text-2)]">:</span>
        <Select value={String(slot.minute)} onValueChange={(v) => onMinute(Number(v))}>
          <SelectTrigger size="sm" className="h-7 w-[70px] text-[11px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {MINUTES.map((m) => (
              <SelectItem key={m} value={String(m)}>
                {String(m).padStart(2, '0')}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {nextRunLabel && slot.enabled && slot.days.length > 0 && (
          <span className="ml-auto text-[10px] text-[var(--text-3)] mono" title={nextRun ?? ''}>
            Next: {nextRunLabel}
          </span>
        )}
      </div>
    </div>
  )
}
