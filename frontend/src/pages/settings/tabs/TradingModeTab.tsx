import { AlertTriangle, Info } from 'lucide-react'
import { Badge, Button, Card } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { useTradingMode } from '@/stores'
import type { TradingMode } from '@/stores'
import { useLiveTradingConfig } from '../useSettingsData'

/**
 * Trading mode selector — picks which account every API call targets.
 * This is a client-side preference, but LIVE switch is guarded by a
 * banner explaining blast radius.
 */
export function TradingModeTab() {
  const mode = useTradingMode((s) => s.mode)
  const setMode = useTradingMode((s) => s.setMode)
  const liveCfg = useLiveTradingConfig()

  return (
    <div className="max-w-[720px] space-y-4">
      <SettingsHeader
        title="Trading mode"
        description="Every query and mutation scopes to this mode. Change between DEMO paper trading and the LIVE agent portfolio."
      />
      <div className="grid grid-cols-2 gap-3">
        <ModeCard
          label="DEMO"
          description="Paper-trading account. All 49 PAPER strategies fill here."
          active={mode === 'DEMO'}
          onClick={() => setMode('DEMO')}
          tone="demo"
        />
        <ModeCard
          label="LIVE"
          description={`Agent portfolio · mirror ratio ${Math.round((Number(liveCfg.data?.mirror_ratio ?? 0)) * 100)}%`}
          active={mode === 'LIVE'}
          onClick={() => setMode('LIVE')}
          tone="live"
        />
      </div>
      {mode === 'LIVE' && (
        <div className="flex items-start gap-2 rounded-[3px] border border-[var(--status-warning)] bg-[color-mix(in_oklab,var(--status-warning)_8%,var(--bg-1))] px-3 py-2 text-[11px]">
          <AlertTriangle className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--status-warning)]" />
          <div>
            <div className="font-medium text-[var(--text-0)]">LIVE mode active</div>
            <div className="text-[var(--text-2)] mt-0.5">
              Mutations from Book, Strategies and Guard target the real eToro account. Toggle back
              to DEMO before experimenting.
            </div>
          </div>
        </div>
      )}
      <Card padding="sm" className="flex items-start gap-2">
        <Info className="h-3.5 w-3.5 mt-0.5 shrink-0 text-[var(--accent-primary)]" />
        <div className="text-[11px] leading-[15px] text-[var(--text-2)]">
          Mode is persisted in <code className="mono text-[10px]">localStorage.alphacent.trading-mode</code>.
          The MetricsBar and TopNavBar reflect the active mode immediately.
        </div>
      </Card>
    </div>
  )
}

function SettingsHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="space-y-1">
      <SectionLabel className="mb-0">{title}</SectionLabel>
      <p className="text-[12px] text-[var(--text-2)] max-w-[720px]">{description}</p>
    </div>
  )
}

function ModeCard({
  label,
  description,
  active,
  onClick,
  tone,
}: {
  label: string
  description: string
  active: boolean
  onClick: () => void
  tone: 'demo' | 'live'
}) {
  const modeValue: TradingMode = label as TradingMode
  return (
    <Card
      interactive
      padding="md"
      onClick={onClick}
      className={
        active
          ? `border-[var(--${tone === 'live' ? 'pnl-up' : 'accent-primary'})] bg-[color-mix(in_oklab,var(--${tone === 'live' ? 'pnl-up' : 'accent-primary'})_4%,var(--bg-1))]`
          : ''
      }
      role="button"
      aria-pressed={active}
      data-active={active}
    >
      <div className="flex items-center justify-between">
        <Badge variant={tone}>{label}</Badge>
        {active && (
          <Button size="sm" variant="ghost" onClick={onClick}>
            Selected
          </Button>
        )}
      </div>
      <p className="mt-2 text-[11px] text-[var(--text-2)]">{description}</p>
      <input
        type="radio"
        name="trading-mode"
        checked={active}
        onChange={() => onClick()}
        value={modeValue}
        className="sr-only"
        aria-label={label}
      />
    </Card>
  )
}
