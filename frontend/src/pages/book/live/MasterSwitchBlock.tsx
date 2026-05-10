import { useState } from 'react'
import { AlertTriangle, Power } from 'lucide-react'
import {
  ConfirmDialog,
  Switch,
} from '@/components/primitives'
import { toast } from 'sonner'
import { cn, formatCurrency } from '@/lib/utils'
import { classifyError } from '@/lib/errors'
import {
  useLiveConfig,
  useLiveSummary,
  useUpdateLiveConfig,
} from '../useBookData'

/**
 * Master switch for live trading.
 *
 * Three visual states:
 *  - OFF (grey) — no live fills happen regardless of strategy authorisations.
 *  - ON / no-auth (amber pulsing) — fills would happen but zero (template,symbol)
 *    pairs are approved. Safe.
 *  - ON / active (emerald solid) — live fills will happen for approved pairs
 *    when conviction clears the threshold.
 *
 * Turning OFF with live positions open doesn't close them; it only prevents
 * NEW fills. We surface that explicitly in the confirmation dialog.
 */
export function MasterSwitchBlock() {
  const config = useLiveConfig()
  const summary = useLiveSummary()
  const update = useUpdateLiveConfig()
  const [confirming, setConfirming] = useState<'on' | 'off' | null>(null)

  const enabled = Boolean(config.data?.enabled)
  const openPositions = summary.data?.open_positions ?? 0
  const authCount = summary.data?.active_live_authorizations ?? 0
  const clientConfigured = config.data?.live_client_configured ?? false

  const state: 'off' | 'on-no-auth' | 'on-active' = !enabled
    ? 'off'
    : authCount === 0
      ? 'on-no-auth'
      : 'on-active'

  const borderColour =
    state === 'off'
      ? 'border-[var(--border-default)]'
      : state === 'on-no-auth'
        ? 'border-[var(--status-warning)]'
        : 'border-[var(--account-live)]'

  const headlineColour =
    state === 'off'
      ? 'text-[var(--text-2)]'
      : state === 'on-no-auth'
        ? 'text-[var(--status-warning)]'
        : 'text-[var(--account-live)]'

  const headline =
    state === 'off'
      ? 'Live trading OFF'
      : state === 'on-no-auth'
        ? 'Live trading ON · 0 authorisations'
        : `Live trading ON · ${authCount} active`

  const subheadline =
    state === 'off'
      ? 'No real-money fills. Paper trading continues normally on DEMO.'
      : state === 'on-no-auth'
        ? 'Master switch is on but no (template, symbol) pairs have been graduated. Go to Strategies → Graduation to promote a pair.'
        : `Real fills will trigger when conviction ≥ ${config.data?.conviction_threshold ?? 74} (${config.data?.conviction_threshold_crypto ?? 68} for crypto).`

  const handleToggle = (next: boolean) => {
    if (!clientConfigured && next) {
      toast.warning('Live eToro client not configured', {
        description: 'Add live credentials in Settings → Live Trading before enabling.',
      })
      return
    }
    setConfirming(next ? 'on' : 'off')
  }

  const commit = async () => {
    const next = confirming === 'on'
    try {
      await update.mutateAsync({ enabled: next })
      toast.success(next ? 'Live trading enabled' : 'Live trading disabled')
    } catch (e) {
      const info = classifyError(e, 'update live config')
      toast.error(info.title, { description: info.message })
    } finally {
      setConfirming(null)
    }
  }

  const confirmDescription =
    confirming === 'on' ? (
      <div className="flex flex-col gap-2">
        <p>
          Enabling live trading means real fills will execute through eToro for
          every approved (template, symbol) pair when their signals fire.
        </p>
        <p>
          Mirror ratio{' '}
          <span className="mono">{((config.data?.mirror_ratio ?? 0.1) * 100).toFixed(0)}%</span>{' '}
          — a{' '}
          <span className="mono">
            {formatCurrency(config.data?.min_order_size ?? 200, { precision: 0 })}
          </span>{' '}
          virtual order becomes{' '}
          <span className="mono">
            {formatCurrency(config.data?.real_per_virtual_order ?? 20, { precision: 0 })}
          </span>{' '}
          real; max{' '}
          <span className="mono">
            {formatCurrency(config.data?.max_real_per_order ?? 150, { precision: 0 })}
          </span>{' '}
          per order.
        </p>
      </div>
    ) : (
      <div className="flex flex-col gap-2">
        <p>Disabling stops new live fills immediately.</p>
        {openPositions > 0 && (
          <p className="flex items-start gap-1.5 p-2 rounded-[3px] bg-[var(--status-warning-bg)] text-[var(--status-warning)]">
            <AlertTriangle className="h-3.5 w-3.5 mt-[1px] shrink-0" />
            <span>
              You have <span className="mono font-semibold">{openPositions}</span> open live
              position{openPositions === 1 ? '' : 's'}. They stay open and continue to be
              monitored — disabling only blocks new orders, it does not close existing ones.
            </span>
          </p>
        )}
        <p className="text-[var(--text-2)]">
          Paper trading on DEMO keeps running. Re-enable at any time.
        </p>
      </div>
    )

  return (
    <>
      <div
        className={cn(
          'rounded-[4px] border-2 bg-[var(--bg-1)] p-3 flex items-center gap-3 transition-colors',
          borderColour,
        )}
      >
        <div
          className={cn(
            'h-10 w-10 rounded-[4px] flex items-center justify-center shrink-0',
            state === 'off'
              ? 'bg-[var(--bg-2)] text-[var(--text-3)]'
              : state === 'on-no-auth'
                ? 'bg-[var(--status-warning-bg)] text-[var(--status-warning)] animate-pulse'
                : 'bg-[color-mix(in_oklab,var(--account-live)_12%,transparent)] text-[var(--account-live)]',
          )}
        >
          <Power className="h-5 w-5" />
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn('text-[14px] font-semibold', headlineColour)}>{headline}</div>
          <p className="text-[11px] text-[var(--text-2)] leading-[16px]">{subheadline}</p>
        </div>
        <div className="shrink-0 flex items-center gap-3">
          {!clientConfigured && (
            <span className="text-[10px] text-[var(--status-error)] uppercase tracking-wide">
              Client not configured
            </span>
          )}
          <Switch
            aria-label="Master live trading switch"
            checked={enabled}
            disabled={config.isLoading || update.isPending}
            onCheckedChange={handleToggle}
            variant={enabled ? 'live' : 'default'}
          />
        </div>
      </div>
      {confirming === 'on' && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setConfirming(null)}
          title="Enable live trading"
          description={confirmDescription}
          confirmLabel="Enable live"
          confirmVariant="live"
          isLoading={update.isPending}
          onConfirm={commit}
        />
      )}
      {confirming === 'off' && (
        <ConfirmDialog
          open
          onOpenChange={(o) => !o && setConfirming(null)}
          title="Disable live trading"
          description={confirmDescription}
          confirmLabel="Disable"
          confirmVariant="destructive"
          isLoading={update.isPending}
          onConfirm={commit}
        />
      )}
    </>
  )
}
