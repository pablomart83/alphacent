import { useState } from 'react'
import { toast } from 'sonner'
import { PowerOff, RefreshCw } from 'lucide-react'
import {
  Button,
  ConfirmDialog,
} from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import {
  useKillSwitch,
  useResetSystem,
  useSystemStatus,
  type KillSwitchResponse,
} from './useGuardData'

/**
 * KillSwitchCard — emergency halt + reset from emergency.
 * Proper fix on success: shows positions closed / orders cancelled count from
 * the backend response so the operator sees the blast radius in one place.
 */
export function KillSwitchCard() {
  const status = useSystemStatus()
  const kill = useKillSwitch()
  const reset = useResetSystem()
  const [killOpen, setKillOpen] = useState(false)
  const [resetOpen, setResetOpen] = useState(false)

  const state = status.data?.state
  const isHalted = state === 'EMERGENCY_HALT'

  const handleKill = async () => {
    try {
      const res: KillSwitchResponse = await kill.mutateAsync()
      toast.error('Kill switch fired', {
        description: `${res.positions_closed ?? 0} positions closed · ${res.orders_cancelled ?? 0} orders cancelled`,
      })
      setKillOpen(false)
    } catch (err) {
      const info = classifyError(err, 'kill switch')
      toast.error(info.title, { description: info.message })
    }
  }

  const handleReset = async () => {
    try {
      await reset.mutateAsync()
      toast.success('System reset — returned to STOPPED')
      setResetOpen(false)
    } catch (err) {
      const info = classifyError(err, 'reset system')
      toast.error(info.title, { description: info.message })
    }
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Emergency</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-2">
        {isHalted ? (
          <>
            <div className="text-[10px] text-[var(--pnl-down)] font-medium uppercase tracking-wider">
              System is in EMERGENCY_HALT
            </div>
            <p className="text-[10px] text-[var(--text-2)]">
              Signal generation and order execution are stopped. Reset returns the system
              to STOPPED — you can then Start from the Cycle page.
            </p>
            <Button
              variant="primary"
              size="sm"
              onClick={() => setResetOpen(true)}
              className="w-full gap-1.5"
            >
              <RefreshCw className="h-3.5 w-3.5" />
              Reset system state
            </Button>
          </>
        ) : (
          <>
            <p className="text-[10px] text-[var(--text-2)]">
              Kill switch closes every open position and cancels every pending order.
              Used only for genuine emergencies — slippage on forced exits is non-trivial.
            </p>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => setKillOpen(true)}
              className="w-full gap-1.5"
              disabled={state === 'STOPPED'}
            >
              <PowerOff className="h-3.5 w-3.5" />
              Fire kill switch
            </Button>
            {state === 'STOPPED' && (
              <div className="text-[9px] text-[var(--text-3)]">
                System is already STOPPED — nothing to halt.
              </div>
            )}
          </>
        )}
      </div>

      <ConfirmDialog
        open={killOpen}
        onOpenChange={setKillOpen}
        title="Fire kill switch"
        description="This closes every open position at market price and cancels every pending order across both DEMO and LIVE accounts. Slippage on forced exits can be material. Only fire if you need to stop trading right now."
        confirmLabel="Fire kill switch"
        confirmVariant="destructive"
        isLoading={kill.isPending}
        onConfirm={handleKill}
      />

      <ConfirmDialog
        open={resetOpen}
        onOpenChange={setResetOpen}
        title="Reset from emergency halt"
        description="Returns the system to STOPPED state. You'll need to start autonomous trading explicitly from the Strategies / Cycle tab."
        confirmLabel="Reset"
        confirmVariant="primary"
        isLoading={reset.isPending}
        onConfirm={handleReset}
      />
    </section>
  )
}
