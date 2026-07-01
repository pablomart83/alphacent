import { useMemo } from 'react'
import { AlertTriangle, CheckCircle2 } from 'lucide-react'
import { cn, coerceToDate } from '@/lib/utils'
import { useRiskMetrics, useSystemHealth, type TradingGate } from '@/pages/guard/useGuardData'
import { useLiveDivergence } from '@/pages/book/useBookData'

type Severity = 'danger' | 'warning' | 'info'

interface AlertRow {
  severity: Severity
  label: string
  detail?: string
}

const SEV_ORDER: Record<Severity, number> = { danger: 0, warning: 1, info: 2 }
const SEV_COLOR: Record<Severity, string> = {
  danger: 'var(--pnl-down)',
  warning: 'var(--status-warning)',
  info: 'var(--accent-primary)',
}

function ageSeconds(v: string | number | null): number | null {
  const d = coerceToDate(v)
  return d ? (Date.now() - d.getTime()) / 1000 : null
}

interface AlertsPanelProps {
  dataUpdatedAt: number | null
  lastSyncAt: string | null
  systemState: string | null
}

/**
 * Fund-level "what needs a decision" — NOT internal Kiro/Intel dev findings.
 * Aggregates live risk-limit breaches, stale data / reconciliation, trading-gate
 * or kill-switch blocks, and live-vs-walk-forward divergence.
 */
export function AlertsPanel({ dataUpdatedAt, lastSyncAt, systemState }: AlertsPanelProps) {
  const liveRisk = useRiskMetrics('LIVE')
  const health = useSystemHealth()
  const divergence = useLiveDivergence()

  const alerts = useMemo<AlertRow[]>(() => {
    const out: AlertRow[] = []

    // Live risk-limit breaches
    const score = liveRisk.data?.risk_score
    const reasons = liveRisk.data?.risk_reasons ?? []
    if (score && score !== 'safe') {
      for (const reason of reasons.slice(0, 4)) {
        out.push({ severity: score === 'danger' ? 'danger' : 'warning', label: reason })
      }
    }

    // System state / kill switch
    if (systemState && !systemState.toLowerCase().includes('run')) {
      out.push({ severity: 'danger', label: `Trading system: ${systemState}`, detail: 'Not running' })
    }

    // Trading gates blocking
    const gates = (health.data?.trading_gates ?? []) as TradingGate[]
    for (const g of gates.filter((x) => x.blocking).slice(0, 3)) {
      out.push({ severity: 'warning', label: `Gate blocking: ${g.name}`, detail: g.detail ?? undefined })
    }

    // Stale data / reconciliation
    const dataAge = ageSeconds(dataUpdatedAt)
    if (dataAge != null && dataAge > 300) {
      out.push({
        severity: dataAge > 900 ? 'danger' : 'warning',
        label: 'Market data stale',
        detail: `${Math.round(dataAge / 60)}m since update`,
      })
    }
    const syncAge = ageSeconds(lastSyncAt)
    if (syncAge != null && syncAge > 90 * 60) {
      out.push({
        severity: syncAge > 180 * 60 ? 'danger' : 'warning',
        label: 'Position reconciliation stale',
        detail: `${Math.round(syncAge / 60)}m since sync`,
      })
    }

    // Live vs walk-forward divergence
    const flagged = divergence.data?.divergence?.filter((d) => d.divergence_flag) ?? []
    if (flagged.length > 0) {
      out.push({
        severity: 'warning',
        label: `${flagged.length} live strateg${flagged.length === 1 ? 'y' : 'ies'} diverging from WF`,
        detail: flagged.slice(0, 6).map((d) => d.symbol).join(', '),
      })
    }

    return out.sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity])
  }, [liveRisk.data, health.data, divergence.data, dataUpdatedAt, lastSyncAt, systemState])

  if (alerts.length === 0) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-center text-[var(--text-3)]">
        <CheckCircle2 className="h-5 w-5 text-[var(--pnl-up)]" />
        <span className="text-[11px]">All clear — no risk breaches, stale data, or divergence.</span>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {alerts.map((a, i) => (
        <div
          key={i}
          className="flex items-start gap-2 rounded-[3px] border p-2"
          style={{
            borderColor: `color-mix(in oklab, ${SEV_COLOR[a.severity]} 35%, transparent)`,
            background: `color-mix(in oklab, ${SEV_COLOR[a.severity]} 6%, var(--bg-1))`,
          }}
        >
          <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" style={{ color: SEV_COLOR[a.severity] }} />
          <div className="min-w-0">
            <div className={cn('text-[11px] font-medium text-[var(--text-0)]')}>{a.label}</div>
            {a.detail && <div className="text-[10px] text-[var(--text-2)] mono truncate">{a.detail}</div>}
          </div>
        </div>
      ))}
    </div>
  )
}
