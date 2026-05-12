import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import {
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
import { LiveTradingHealthCard } from './LiveTradingHealthCard'
import { GatesTab } from './gates/GatesTab'
import { RiskTab } from './risk/RiskTab'
import { SystemTab } from './system/SystemTab'
import { CircuitBreakersTab } from './breakers/CircuitBreakersTab'
import { AlertsTab } from './alerts/AlertsTab'
import { AuditTab } from './audit/AuditTab'
import { useRiskLimits, useRiskMetrics } from './useGuardData'

/**
 * Guard surface — /guard.
 *
 * Tabs: Risk · Gates · System · Circuit Breakers · Alerts · Audit.
 * Left panel (RiskScoreHero + RiskMetricTiles + LimitEditor + KillSwitchCard)
 * is permanent across all tabs.
 */

type TabValue = 'system' | 'risk' | 'gates' | 'circuit-breakers' | 'alerts' | 'audit'

const TABS: Array<{ value: TabValue; label: string }> = [
  { value: 'system', label: 'System' },
  { value: 'risk', label: 'Risk' },
  { value: 'gates', label: 'Gates' },
  { value: 'circuit-breakers', label: 'Circuit breakers' },
  { value: 'alerts', label: 'Alerts' },
  { value: 'audit', label: 'Audit' },
]

export function Guard() {
  return (
    <Routes>
      <Route index element={<Navigate to="/guard/system" replace />} />
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
    current === 'system'
      ? 'System health · data sync'
      : current === 'risk'
        ? `Risk · ${mode}`
        : current === 'gates'
          ? 'Trading gates'
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
      <LiveTradingHealthCard />
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
          ) : current === 'system' ? (
            <SystemTab />
          ) : current === 'circuit-breakers' ? (
            <CircuitBreakersTab />
          ) : current === 'alerts' ? (
            <AlertsTab />
          ) : (
            <AuditTab />
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
