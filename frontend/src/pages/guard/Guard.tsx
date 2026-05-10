import { Hammer } from 'lucide-react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import {
  EmptyState,
  Tabs,
  TabsList,
  TabsTrigger,
} from '@/components/primitives'
import { PageTemplate, ResizablePanelLayout } from '@/components/layout'
import { useTradingMode } from '@/stores'
import { KillSwitchCard } from './KillSwitchCard'
import { LimitEditor } from './LimitEditor'
import { RiskMetricTiles } from './RiskMetricTiles'
import { RiskScoreHero } from './RiskScoreHero'
import { GatesTab } from './gates/GatesTab'
import { RiskTab } from './risk/RiskTab'
import { useRiskLimits, useRiskMetrics } from './useGuardData'

/**
 * Guard surface — /guard.
 *
 * Tabs: Risk · Gates · System · Circuit Breakers · Alerts · Audit.
 * Sprint 8 ships Risk + Gates; the remaining four render scoped ComingSoon
 * cards pointing at Sprint 9. Left panel (RiskScoreHero + RiskMetricTiles
 * + LimitEditor + KillSwitchCard) is permanent across all tabs.
 */

type TabValue = 'risk' | 'gates' | 'system' | 'circuit-breakers' | 'alerts' | 'audit'

const TABS: Array<{ value: TabValue; label: string; sprint?: number }> = [
  { value: 'risk', label: 'Risk' },
  { value: 'gates', label: 'Gates' },
  { value: 'system', label: 'System', sprint: 9 },
  { value: 'circuit-breakers', label: 'Circuit breakers', sprint: 9 },
  { value: 'alerts', label: 'Alerts', sprint: 9 },
  { value: 'audit', label: 'Audit', sprint: 9 },
]

export function Guard() {
  return (
    <Routes>
      <Route index element={<Navigate to="/guard/risk" replace />} />
      <Route path=":tab/*" element={<GuardShell />} />
    </Routes>
  )
}

function GuardShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)
  const metrics = useRiskMetrics()
  const limits = useRiskLimits()

  const parts = location.pathname.split('/').filter(Boolean)
  const rawTab = parts[1] || 'risk'
  const current: TabValue =
    (TABS.find((t) => t.value === rawTab)?.value as TabValue) ?? 'risk'

  const description =
    current === 'risk'
      ? `Risk · ${mode}`
      : current === 'gates'
        ? 'Trading gates'
        : current === 'system'
          ? 'System health'
          : current === 'circuit-breakers'
            ? 'Circuit breakers'
            : current === 'alerts'
              ? 'Alerts'
              : 'Audit log'

  const leftPanel = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-2 py-3 space-y-3">
      <RiskScoreHero metrics={metrics.data} loading={metrics.isLoading} />
      <RiskMetricTiles
        metrics={metrics.data}
        limits={limits.data}
        loading={metrics.isLoading || limits.isLoading}
      />
      <LimitEditor
        limits={limits.data}
        metrics={metrics.data}
        loading={limits.isLoading}
      />
      <KillSwitchCard />
    </div>
  )

  const rightPanel = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
      <Tabs
        value={current}
        onValueChange={(v) => navigate(`/guard/${v}`)}
        className="flex flex-col h-full min-h-0"
      >
        <TabsList className="shrink-0 px-2 pt-1 border-b border-[var(--border-subtle)] bg-[var(--bg-0)]">
          {TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="flex-1 min-h-0">
          {current === 'risk' ? (
            <RiskTab />
          ) : current === 'gates' ? (
            <GatesTab />
          ) : (
            <ComingSoonCard
              tab={current}
              sprint={TABS.find((t) => t.value === current)?.sprint ?? 9}
            />
          )}
        </div>
      </Tabs>
    </div>
  )

  return (
    <PageTemplate title="Guard" description={description}>
      <ResizablePanelLayout
        layoutId="guard"
        panels={[
          {
            id: 'guard-left',
            defaultSize: 30,
            minSize: 22,
            maxSize: 42,
            content: leftPanel,
          },
          {
            id: 'guard-right',
            defaultSize: 70,
            minSize: 50,
            content: rightPanel,
          },
        ]}
      />
    </PageTemplate>
  )
}

function ComingSoonCard({ tab, sprint }: { tab: string; sprint: number }) {
  const copy: Record<string, string> = {
    system:
      'HealthTiles, WebSocket health, MonitoringServiceCard, BackgroundThreadsTable, DataSyncPanel with live log tail, DbStatsCard, DataQualityTable, EventTimeline24h. Ships with Sprint 9.',
    'circuit-breakers':
      'CircuitBreakerGrid (per CB state + trip timeline + reset action). Ships with Sprint 9.',
    alerts:
      'AlertsList, per-alert card with acknowledge/read, bulk actions, AlertPreferences. Ships with Sprint 9.',
    audit:
      'AuditLogVirtualized, filter bar, TradeLifecycleChain drill-down, CSV export. Ships with Sprint 9.',
  }
  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-0)] p-4">
      <EmptyState
        icon={Hammer}
        title={`${tab === 'circuit-breakers' ? 'Circuit breakers' : tab.charAt(0).toUpperCase() + tab.slice(1)} — Sprint ${sprint}`}
        description={copy[tab] ?? `Lands in Sprint ${sprint}.`}
      />
    </div>
  )
}
