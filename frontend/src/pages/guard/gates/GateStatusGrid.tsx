import { useMemo } from 'react'
import {
  AlertOctagon,
  Bitcoin,
  CheckCircle2,
  Clock,
  LineChart,
  Power,
  ShieldAlert,
  ShieldOff,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react'
import { Badge, EmptyState, Skeleton } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { cn } from '@/lib/utils'
import type { TradingGate } from '../useGuardData'

interface GateStatusGridProps {
  gates: TradingGate[] | undefined
  loading?: boolean
}

type GateState = 'clear' | 'warning' | 'blocking'

interface GateDescriptor {
  icon: React.ComponentType<{ className?: string }>
  title: string
  summary: string
}

const GATE_META: Record<string, GateDescriptor> = {
  kill_switch: {
    icon: Power,
    title: 'Kill switch',
    summary:
      'Manual emergency stop. When blocking: no new signals fire, no orders submit. Fired from the Emergency card on the left.',
  },
  market_hours: {
    icon: Clock,
    title: 'Market hours',
    summary:
      'Per-asset-class session check. Equities are closed overnight and weekends; crypto 24/7; forex 24/5. Blocks new entries when the venue for the symbol is shut.',
  },
  vix_gate: {
    icon: TrendingUp,
    title: 'VIX gate (C1)',
    summary:
      'Blocks LONG entries when VIX > 25 AND VIX_5d > +15%. Post-VIX-spike forward returns weaken. Crypto exempt.',
  },
  momentum_crash: {
    icon: TrendingDown,
    title: 'Momentum crash (C2)',
    summary:
      'Soft gate — subtracts 10 from regime_fit for LONG momentum/trend/breakout strategies when SPY_5d < -3% AND VIX_1d > +10%. Surfaces when active.',
  },
  trend_consistency: {
    icon: LineChart,
    title: 'Trend consistency (C3)',
    summary:
      'Blocks counter-trend entries. SHORT blocked above rising 50d SMA; LONG blocked below falling 50d SMA. Catches late-stage reversals.',
  },
  rejection_blacklist: {
    icon: ShieldOff,
    title: 'Rejection blacklist',
    summary:
      '14-day cooldown after a (template × symbol) rejection or 3× consecutive losing trades. Regime-scoped early expiry when the regime flips.',
  },
  freshness_sla: {
    icon: Zap,
    title: 'Freshness SLA',
    summary:
      'Blocks signal generation for symbols whose bar data is stale (older than the strategy timeframe × 2). Stops trading on broken data feeds.',
  },
  circuit_breaker_etoro: {
    icon: AlertOctagon,
    title: 'Circuit breaker — eToro',
    summary:
      'Opens after consecutive API errors. All eToro calls return fast-fail while open; recovers via half-open probes.',
  },
  circuit_breaker_yahoo: {
    icon: AlertOctagon,
    title: 'Circuit breaker — Yahoo',
    summary: 'Opens after consecutive Yahoo Finance outages. Price cache keeps serving stale bars while open.',
  },
  circuit_breaker_fmp: {
    icon: AlertOctagon,
    title: 'Circuit breaker — FMP',
    summary: 'Opens after consecutive Financial Modeling Prep outages. Fundamental checks fall back to cached values.',
  },
  crypto_cycle: {
    icon: Bitcoin,
    title: 'Crypto cycle',
    summary: 'Adjusts conviction for crypto strategies based on halving-cycle phase.',
  },
}

function GENERIC_META(name: string): GateDescriptor {
  return {
    icon: ShieldAlert,
    title: name.replace(/_/g, ' '),
    summary: 'Trading gate defined on the backend but not documented in the UI yet.',
  }
}

function gateState(gate: TradingGate): GateState {
  if (gate.blocking) return 'blocking'
  // Backend sometimes populates `detail` even when not blocking — treat as warning.
  if (gate.detail && gate.detail.trim().length > 0) return 'warning'
  return 'clear'
}

export function GateStatusGrid({ gates, loading }: GateStatusGridProps) {
  const sorted = useMemo(() => {
    const list = gates ?? []
    return list.slice().sort((a, b) => {
      const order = (g: TradingGate) =>
        g.blocking ? 0 : g.detail ? 1 : !g.armed ? 3 : 2
      const delta = order(a) - order(b)
      if (delta !== 0) return delta
      return a.name.localeCompare(b.name)
    })
  }, [gates])

  if (loading && !gates) {
    return (
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {Array.from({ length: 6 }).map((_, i) => (
          <Skeleton key={i} className="h-[130px]" />
        ))}
      </div>
    )
  }

  if (!sorted.length) {
    return (
      <EmptyState
        icon={ShieldAlert}
        title="No gates reported"
        description="The /control/system-health payload returned no trading_gates entries. Check backend observability — Sprint 9 adds circuit-breaker resets."
      />
    )
  }

  return (
    <div className="space-y-2">
      <SectionLabel>Trading gates · {sorted.length}</SectionLabel>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-2">
        {sorted.map((gate) => (
          <GateCard key={gate.name} gate={gate} />
        ))}
      </div>
    </div>
  )
}

function GateCard({ gate }: { gate: TradingGate }) {
  const state = gateState(gate)
  const meta = GATE_META[gate.name] ?? GENERIC_META(gate.name)
  const Icon = meta.icon

  const stateColor =
    state === 'blocking'
      ? 'var(--pnl-down)'
      : state === 'warning'
        ? 'var(--status-warning)'
        : 'var(--pnl-up)'

  const stateLabel =
    state === 'blocking' ? 'Blocking' : state === 'warning' ? 'Watching' : 'Clear'

  const StateIcon =
    state === 'blocking' ? ShieldAlert : state === 'warning' ? ShieldAlert : CheckCircle2

  return (
    <article
      className={cn(
        'rounded-[3px] border bg-[var(--bg-1)] p-2 flex flex-col gap-1.5 transition-colors',
      )}
      style={{
        borderColor:
          state === 'blocking' ? stateColor : 'var(--border-subtle)',
        boxShadow:
          state === 'blocking'
            ? `0 0 0 1px color-mix(in oklab, ${stateColor} 40%, transparent)`
            : undefined,
      }}
    >
      <header className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-1.5 min-w-0">
          <Icon className="h-3.5 w-3.5 text-[var(--text-3)] shrink-0" />
          <span
            className="text-[11px] font-semibold text-[var(--text-0)] uppercase tracking-wider truncate"
            title={meta.title}
          >
            {meta.title}
          </span>
        </div>
        <span
          className={cn(
            'inline-flex items-center gap-1 px-1.5 h-[18px] rounded-[3px] text-[9px] font-semibold uppercase tracking-wider',
            state === 'blocking' && 'animate-pulse',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${stateColor} 15%, transparent)`,
            color: stateColor,
            border: `1px solid color-mix(in oklab, ${stateColor} 40%, transparent)`,
          }}
        >
          <StateIcon className="h-3 w-3" />
          {stateLabel}
        </span>
      </header>

      <div className="flex items-center gap-1.5">
        <Badge
          variant={gate.armed ? 'info' : 'muted'}
          size="sm"
          title={gate.armed ? 'Gate is armed' : 'Gate is disarmed'}
        >
          {gate.armed ? 'Armed' : 'Disarmed'}
        </Badge>
      </div>

      {gate.detail && (
        <p
          className="text-[10px] text-[var(--text-1)] mono break-words"
          title={gate.detail}
        >
          {gate.detail}
        </p>
      )}

      <p className="text-[10px] text-[var(--text-3)] leading-snug">{meta.summary}</p>
    </article>
  )
}
