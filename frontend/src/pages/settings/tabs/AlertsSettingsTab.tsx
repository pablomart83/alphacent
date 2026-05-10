import { useState } from 'react'
import { Bell, Info } from 'lucide-react'
import { Button, Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { AlertPreferencesDialog } from '@/pages/guard/alerts/AlertPreferencesDialog'

/**
 * Alerts settings mirror the Guard surface's Alerts tab preferences.
 * Rather than duplicate the dialog we surface it here and let the CIO
 * open the full editor. Thresholds live in the guarded dialog.
 */
export function AlertsSettingsTab() {
  const [open, setOpen] = useState(false)
  return (
    <div className="max-w-[720px] space-y-3">
      <div className="space-y-1">
        <SectionLabel className="mb-0">Alerts</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          Threshold and routing preferences for the alert engine. Use the full preferences editor
          below — the same dialog ships on the Guard → Alerts tab.
        </p>
      </div>
      <Card padding="md" className="flex items-start gap-2">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--accent-primary)]" />
        <div className="text-[11px] leading-[15px] text-[var(--text-2)]">
          The detailed alert dialog controls PNL loss / gain thresholds, drawdown ceiling,
          per-position loss, margin warning, plus browser push, cycle-complete and
          strategy-retired notifications. Changes persist server-side via AlertConfigORM.
        </div>
      </Card>
      <div className="flex justify-end">
        <Button variant="primary" size="sm" onClick={() => setOpen(true)}>
          <Bell className="h-3 w-3 mr-1" /> Edit alert preferences
        </Button>
      </div>
      <AlertPreferencesDialog open={open} onOpenChange={setOpen} />
    </div>
  )
}
