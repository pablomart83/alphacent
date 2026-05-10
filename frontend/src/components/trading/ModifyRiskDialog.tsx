import { useEffect, useMemo, useState } from 'react'
import { AlertTriangle, Info, X } from 'lucide-react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
} from '@/components/primitives'
import {
  useModifyPositionRisk,
  type PositionRow,
} from '@/pages/book/useBookData'
import { useTradingMode } from '@/stores'
import { notifyError } from '@/lib/errors'
import { cn, formatCurrency, formatPercentage } from '@/lib/utils'
import { toast } from 'sonner'

interface ModifyRiskDialogProps {
  position: PositionRow | null
  open: boolean
  onOpenChange: (open: boolean) => void
}

type NumericInput = '' | string

/** Format a position's current SL/TP into a UI-editable string (blank == not set). */
function toInput(value: number | null): NumericInput {
  if (value == null) return ''
  // Avoid trailing-zero noise but keep enough precision for forex.
  const abs = Math.abs(value)
  const precision = abs > 100 ? 2 : abs > 1 ? 4 : 6
  return value.toFixed(precision).replace(/\.?0+$/, '')
}

function parseInput(value: string): number | null | 'invalid' {
  const trimmed = value.trim()
  if (!trimmed) return null
  const num = Number(trimmed)
  if (!Number.isFinite(num)) return 'invalid'
  return num
}

function distancePct(level: number, entry: number): number {
  if (!entry) return 0
  return ((level - entry) / entry) * 100
}

export function ModifyRiskDialog({ position, open, onOpenChange }: ModifyRiskDialogProps) {
  const mode = useTradingMode((s) => s.mode)
  const mutation = useModifyPositionRisk()

  const [slInput, setSlInput] = useState<NumericInput>('')
  const [tpInput, setTpInput] = useState<NumericInput>('')
  const [clearSL, setClearSL] = useState(false)
  const [clearTP, setClearTP] = useState(false)

  // Reset form whenever we open with a new position.
  useEffect(() => {
    if (position) {
      setSlInput(toInput(position.stop_loss))
      setTpInput(toInput(position.take_profit))
      setClearSL(false)
      setClearTP(false)
    }
  }, [position, open])

  const side = (position?.side || 'LONG').toUpperCase()
  const isLong = side.includes('LONG') || side.includes('BUY')
  const entry = position?.entry_price ?? 0
  const current = position?.current_price ?? 0

  const parsedSL = useMemo(() => (clearSL ? null : parseInput(slInput)), [slInput, clearSL])
  const parsedTP = useMemo(() => (clearTP ? null : parseInput(tpInput)), [tpInput, clearTP])

  const slInvalid = parsedSL === 'invalid'
  const tpInvalid = parsedTP === 'invalid'

  // Client-side previews — the server re-validates and is the source of truth.
  const slWarnings = useMemo(() => {
    const w: string[] = []
    if (parsedSL === null && clearSL) {
      w.push('Clears SL — no downside enforcement until a new SL is set.')
      return w
    }
    if (parsedSL === 'invalid' || parsedSL === null) return w
    const dist = Math.abs(distancePct(parsedSL, entry))
    if (isLong && parsedSL >= entry) w.push(`SL ${parsedSL} is at or above entry ${entry} — rejected for LONG.`)
    if (!isLong && parsedSL <= entry) w.push(`SL ${parsedSL} is at or below entry ${entry} — rejected for SHORT.`)
    if (isLong && parsedSL >= current) w.push(`SL above current price — will trigger on next monitoring tick.`)
    if (!isLong && parsedSL <= current) w.push(`SL below current price — will trigger on next monitoring tick.`)
    if (dist > 20) w.push(`SL distance ${dist.toFixed(1)}% is large — server may reject (caps: stocks 9% · crypto 15% · forex 4%).`)
    return w
  }, [parsedSL, clearSL, isLong, entry, current])

  const tpWarnings = useMemo(() => {
    const w: string[] = []
    if (parsedTP === null && clearTP) return w
    if (parsedTP === 'invalid' || parsedTP === null) return w
    if (isLong && parsedTP <= entry) w.push(`TP ${parsedTP} must be above entry ${entry} for a LONG position.`)
    if (!isLong && parsedTP >= entry) w.push(`TP ${parsedTP} must be below entry ${entry} for a SHORT position.`)
    if (isLong && parsedTP <= current) w.push(`TP at or below current price — will trigger immediately.`)
    if (!isLong && parsedTP >= current) w.push(`TP at or above current price — will trigger immediately.`)
    return w
  }, [parsedTP, clearTP, isLong, entry, current])

  const hasBlockingError = slInvalid || tpInvalid
  const nothingToSave =
    !clearSL &&
    !clearTP &&
    (parsedSL === null ? position?.stop_loss == null : parsedSL === position?.stop_loss) &&
    (parsedTP === null ? position?.take_profit == null : parsedTP === position?.take_profit)

  const handleSubmit = async () => {
    if (!position || hasBlockingError || nothingToSave) return
    const payload: Parameters<typeof mutation.mutateAsync>[0] = {
      positionId: position.id,
      mode,
    }

    // Only include the fields the user touched.
    const originalSL = toInput(position.stop_loss)
    const originalTP = toInput(position.take_profit)

    if (clearSL) {
      payload.stop_loss = null
    } else if (slInput !== originalSL) {
      if (parsedSL === null) payload.stop_loss = null
      else if (typeof parsedSL === 'number') payload.stop_loss = parsedSL
    }
    if (clearTP) {
      payload.take_profit = null
    } else if (tpInput !== originalTP) {
      if (parsedTP === null) payload.take_profit = null
      else if (typeof parsedTP === 'number') payload.take_profit = parsedTP
    }

    if (
      payload.stop_loss === undefined &&
      payload.take_profit === undefined
    ) {
      onOpenChange(false)
      return
    }

    try {
      const res = await mutation.mutateAsync(payload)
      if (res.warnings?.length) {
        toast.warning('Risk levels updated with warnings', {
          description: res.warnings.join(' · '),
          duration: 6000,
        })
      } else {
        toast.success('Risk levels updated')
      }
      onOpenChange(false)
    } catch (err) {
      notifyError(err, 'modify SL/TP')
    }
  }

  if (!position) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>Modify risk levels</DialogTitle>
          <DialogDescription>
            {position.symbol} · {side} · entry {formatCurrency(entry, { precision: 4 })} ·{' '}
            current {formatCurrency(current, { precision: 4 })}
          </DialogDescription>
        </DialogHeader>

        <div className="mt-1 mb-3 flex items-start gap-2 rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-2)] px-2.5 py-2">
          <Info className="h-3.5 w-3.5 mt-[2px] text-[var(--accent-primary)] shrink-0" />
          <p className="text-[11px] leading-[16px] text-[var(--text-2)]">
            Stops are enforced by AlphaCent's monitoring service every 60 seconds (DB-side).
            This writes the authoritative value. eToro does not support SL modification via
            API so the stored level is the enforcement, not an eToro-side stop.
          </p>
        </div>

        <div className="flex flex-col gap-3">
          <RiskField
            label="Stop-loss"
            input={slInput}
            onChange={(v) => {
              setSlInput(v)
              setClearSL(false)
            }}
            onClear={() => {
              setSlInput('')
              setClearSL(true)
            }}
            cleared={clearSL}
            entry={entry}
            parsed={parsedSL}
            warnings={slWarnings}
            invalid={slInvalid}
            placeholder={isLong ? `< ${entry}` : `> ${entry}`}
          />
          <RiskField
            label="Take-profit"
            input={tpInput}
            onChange={(v) => {
              setTpInput(v)
              setClearTP(false)
            }}
            onClear={() => {
              setTpInput('')
              setClearTP(true)
            }}
            cleared={clearTP}
            entry={entry}
            parsed={parsedTP}
            warnings={tpWarnings}
            invalid={tpInvalid}
            placeholder={isLong ? `> ${entry}` : `< ${entry}`}
          />
        </div>

        <DialogFooter className="mt-4">
          <Button
            variant="ghost"
            onClick={() => onOpenChange(false)}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="primary"
            onClick={handleSubmit}
            disabled={hasBlockingError || nothingToSave}
            loading={mutation.isPending}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function RiskField({
  label,
  input,
  onChange,
  onClear,
  cleared,
  entry,
  parsed,
  warnings,
  invalid,
  placeholder,
}: {
  label: string
  input: NumericInput
  onChange: (v: string) => void
  onClear: () => void
  cleared: boolean
  entry: number
  parsed: number | null | 'invalid'
  warnings: string[]
  invalid: boolean
  placeholder?: string
}) {
  const showDistance =
    typeof parsed === 'number' && Number.isFinite(parsed) && entry > 0 && !cleared
  const dist = showDistance ? distancePct(parsed as number, entry) : 0

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <Label className="text-[11px]">{label}</Label>
        <div className="flex items-center gap-2">
          {showDistance && (
            <span
              className={cn(
                'text-[10px] mono tabular-nums',
                Math.abs(dist) > 15 ? 'text-[var(--status-warning)]' : 'text-[var(--text-3)]',
              )}
            >
              {formatPercentage(dist, { signed: true, precision: 2 })}
            </span>
          )}
          {!cleared && (
            <button
              type="button"
              onClick={onClear}
              className="text-[10px] text-[var(--text-3)] hover:text-[var(--status-error)] transition-colors inline-flex items-center gap-0.5"
            >
              <X className="h-2.5 w-2.5" /> clear
            </button>
          )}
        </div>
      </div>
      <Input
        type="number"
        step="any"
        inputMode="decimal"
        value={cleared ? '' : input}
        placeholder={cleared ? '(cleared)' : placeholder}
        error={invalid}
        onChange={(e) => onChange(e.target.value)}
        className="mono"
      />
      {cleared && (
        <div className="flex items-start gap-1.5 text-[10px] text-[var(--status-warning)]">
          <AlertTriangle className="h-3 w-3 mt-[1px] shrink-0" />
          <span>Level will be cleared on save.</span>
        </div>
      )}
      {warnings.length > 0 && (
        <ul className="flex flex-col gap-0.5">
          {warnings.map((w, i) => (
            <li
              key={i}
              className="flex items-start gap-1.5 text-[10px] text-[var(--status-warning)]"
            >
              <AlertTriangle className="h-3 w-3 mt-[1px] shrink-0" />
              <span>{w}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
