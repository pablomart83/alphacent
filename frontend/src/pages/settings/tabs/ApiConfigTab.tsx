import { useState } from 'react'
import { toast } from 'sonner'
import { CheckCircle2, XCircle, Loader2 } from 'lucide-react'
import { Button, Card, Input, Label } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  useConnectionStatus,
  useSetCredentials,
} from '../useSettingsData'
import type { TradingMode } from '@/stores'

/**
 * API config — store eToro keys per mode, test connection.
 * Fields start blank (keys never render back to the UI — secrets stay on
 * server) so an empty form means "no change" rather than "clear".
 */
export function ApiConfigTab() {
  return (
    <div className="max-w-[720px] space-y-6">
      <div className="space-y-1">
        <SectionLabel className="mb-0">API configuration</SectionLabel>
        <p className="text-[12px] text-[var(--text-2)]">
          eToro public + user keys per mode. Keys are stored encrypted; the form does not display
          existing keys — leave fields empty to preserve the stored value.
        </p>
      </div>
      <CredentialForm mode="DEMO" />
      <CredentialForm mode="LIVE" />
    </div>
  )
}

function CredentialForm({ mode }: { mode: TradingMode }) {
  const status = useConnectionStatus(mode)
  const setCreds = useSetCredentials()
  const [publicKey, setPublicKey] = useState('')
  const [userKey, setUserKey] = useState('')

  const onSave = async () => {
    if (!publicKey || !userKey) {
      toast.error('Both keys are required')
      return
    }
    try {
      await setCreds.mutateAsync({ mode, public_key: publicKey, user_key: userKey })
      toast.success(`${mode} credentials saved`)
      setPublicKey('')
      setUserKey('')
    } catch (err) {
      toast.error(classifyError(err, 'saving credentials').message)
    }
  }

  return (
    <Card padding="md" className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-[12px] font-medium text-[var(--text-0)]">{mode} credentials</h3>
        <StatusPill
          loading={status.isLoading}
          connected={status.data?.connected ?? false}
          message={status.data?.message}
        />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
            Public key
          </Label>
          <Input
            value={publicKey}
            onChange={(e) => setPublicKey(e.target.value)}
            placeholder="Leave blank to keep existing"
            className="mono text-[11px]"
            autoComplete="off"
          />
        </div>
        <div className="space-y-1">
          <Label className="text-[10px] uppercase tracking-wider text-[var(--text-3)]">
            User key
          </Label>
          <Input
            value={userKey}
            onChange={(e) => setUserKey(e.target.value)}
            placeholder="Leave blank to keep existing"
            className="mono text-[11px]"
            autoComplete="off"
            type="password"
          />
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-1 border-t border-[var(--border-subtle)]">
        <Button variant="ghost" size="sm" onClick={() => status.refetch()}>
          Test connection
        </Button>
        <Button
          variant="primary"
          size="sm"
          onClick={onSave}
          loading={setCreds.isPending}
          disabled={!publicKey || !userKey}
        >
          Save {mode}
        </Button>
      </div>
    </Card>
  )
}

function StatusPill({
  loading,
  connected,
  message,
}: {
  loading: boolean
  connected: boolean
  message?: string
}) {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-[var(--text-3)]">
        <Loader2 className="h-3 w-3 animate-spin" /> Checking…
      </span>
    )
  }
  return (
    <span
      className={
        'inline-flex items-center gap-1 text-[10px] ' +
        (connected ? 'text-[var(--pnl-up)]' : 'text-[var(--pnl-down)]')
      }
      title={message}
    >
      {connected ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
      {connected ? 'Connected' : 'Not connected'}
    </span>
  )
}
