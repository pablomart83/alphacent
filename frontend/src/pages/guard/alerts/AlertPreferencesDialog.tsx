import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import {
  Button,
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  Input,
  Label,
  Switch,
} from '@/components/primitives'
import { notifyError } from '@/lib/errors'
import {
  useAlertConfig,
  useUpdateAlertConfig,
  type AlertConfigPayload,
} from '../useGuardData'

interface AlertPreferencesDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

type ConfigShape = AlertConfigPayload['data']

export function AlertPreferencesDialog({ open, onOpenChange }: AlertPreferencesDialogProps) {
  const config = useAlertConfig()
  const update = useUpdateAlertConfig()
  const [draft, setDraft] = useState<ConfigShape | null>(null)

  useEffect(() => {
    if (config.data?.data) setDraft({ ...config.data.data })
  }, [config.data, open])

  const setField = <K extends keyof ConfigShape>(key: K, value: ConfigShape[K]) => {
    if (!draft) return
    setDraft({ ...draft, [key]: value })
  }

  const save = async () => {
    if (!draft) return
    try {
      await update.mutateAsync(draft)
      toast.success('Alert preferences saved')
      onOpenChange(false)
    } catch (err) {
      notifyError(err, 'save alert preferences')
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Alert preferences</DialogTitle>
        </DialogHeader>
        {draft ? (
          <div className="space-y-3 max-h-[60vh] overflow-auto pr-1">
            <ThresholdRow
              label="P&L loss (daily)"
              enabled={draft.pnl_loss_enabled}
              threshold={draft.pnl_loss_threshold}
              unit="$"
              onEnabled={(v) => setField('pnl_loss_enabled', v)}
              onThreshold={(v) => setField('pnl_loss_threshold', v)}
              step={100}
              min={0}
            />
            <ThresholdRow
              label="P&L gain (daily)"
              enabled={draft.pnl_gain_enabled}
              threshold={draft.pnl_gain_threshold}
              unit="$"
              onEnabled={(v) => setField('pnl_gain_enabled', v)}
              onThreshold={(v) => setField('pnl_gain_threshold', v)}
              step={100}
              min={0}
            />
            <ThresholdRow
              label="Portfolio drawdown"
              enabled={draft.drawdown_enabled}
              threshold={draft.drawdown_threshold}
              unit="%"
              onEnabled={(v) => setField('drawdown_enabled', v)}
              onThreshold={(v) => setField('drawdown_threshold', v)}
              step={0.5}
              min={0}
              max={100}
            />
            <ThresholdRow
              label="Position loss"
              enabled={draft.position_loss_enabled}
              threshold={draft.position_loss_threshold}
              unit="%"
              onEnabled={(v) => setField('position_loss_enabled', v)}
              onThreshold={(v) => setField('position_loss_threshold', v)}
              step={0.5}
              min={0}
              max={100}
            />
            <ThresholdRow
              label="Margin utilisation"
              enabled={draft.margin_enabled}
              threshold={draft.margin_threshold}
              unit="%"
              onEnabled={(v) => setField('margin_enabled', v)}
              onThreshold={(v) => setField('margin_threshold', v)}
              step={1}
              min={0}
              max={100}
            />
            <hr className="border-[var(--border-subtle)]" />
            <ToggleRow
              label="Cycle complete notifications"
              value={draft.cycle_complete_enabled}
              onChange={(v) => setField('cycle_complete_enabled', v)}
            />
            <ToggleRow
              label="Strategy retirement notifications"
              value={draft.strategy_retired_enabled}
              onChange={(v) => setField('strategy_retired_enabled', v)}
            />
            <ToggleRow
              label="Browser push (desktop notifications)"
              value={draft.browser_push_enabled}
              onChange={(v) => setField('browser_push_enabled', v)}
            />
          </div>
        ) : (
          <p className="text-[11px] text-[var(--text-3)]">Loading preferences…</p>
        )}
        <DialogFooter>
          <Button variant="ghost" size="sm" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            variant="primary"
            size="sm"
            onClick={save}
            loading={update.isPending}
            disabled={!draft}
          >
            Save
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

interface ThresholdRowProps {
  label: string
  enabled: boolean
  threshold: number
  unit: string
  onEnabled: (v: boolean) => void
  onThreshold: (v: number) => void
  step: number
  min: number
  max?: number
}

function ThresholdRow({
  label,
  enabled,
  threshold,
  unit,
  onEnabled,
  onThreshold,
  step,
  min,
  max,
}: ThresholdRowProps) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Label className="text-[11px] text-[var(--text-1)] flex-1">{label}</Label>
      <div className="flex items-center gap-2">
        <Switch checked={enabled} onCheckedChange={onEnabled} />
        <div className="relative">
          <Input
            type="number"
            value={threshold}
            onChange={(e) => onThreshold(Number(e.target.value))}
            step={step}
            min={min}
            max={max}
            disabled={!enabled}
            className="h-7 w-[88px] mono tabular-nums pr-6 text-[11px] text-right"
          />
          <span className="absolute right-2 top-1/2 -translate-y-1/2 text-[10px] text-[var(--text-3)] pointer-events-none">
            {unit}
          </span>
        </div>
      </div>
    </div>
  )
}

function ToggleRow({
  label,
  value,
  onChange,
}: {
  label: string
  value: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <Label className="text-[11px] text-[var(--text-1)] flex-1">{label}</Label>
      <Switch checked={value} onCheckedChange={onChange} />
    </div>
  )
}
