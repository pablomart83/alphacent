import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { cn } from '@/lib/utils'
import { PageTemplate, ResizablePanelLayout } from '@/components/layout'
import { TradingModeTab } from './tabs/TradingModeTab'
import { ApiConfigTab } from './tabs/ApiConfigTab'
import { RiskLimitsTab } from './tabs/RiskLimitsTab'
import { PositionManagementTab } from './tabs/PositionManagementTab'
import { AutonomousTab } from './tabs/AutonomousTab'
import { AlphaEdgeSettingsTab } from './tabs/AlphaEdgeSettingsTab'
import { AlertsSettingsTab } from './tabs/AlertsSettingsTab'
import { LiveTradingSettingsTab } from './tabs/LiveTradingSettingsTab'
import { UsersTab } from './tabs/UsersTab'
import { ShortcutsTab } from './tabs/ShortcutsTab'

/**
 * Settings surface — /settings, keyboard `g ,`.
 *
 * Vertical tab rail on the left, scrollable form on the right. Each tab
 * owns its own SaveBar so changes on one tab don't bleed into another.
 * The rail persists width via the existing ResizablePanelLayout pattern
 * so CIOs can tune the form column per their monitor size.
 */

type TabValue =
  | 'trading-mode'
  | 'api-config'
  | 'risk-limits'
  | 'position-management'
  | 'autonomous'
  | 'alpha-edge'
  | 'alerts'
  | 'live-trading'
  | 'users'
  | 'shortcuts'

const TABS: Array<{ value: TabValue; label: string; group?: string }> = [
  { value: 'trading-mode', label: 'Trading mode', group: 'Account' },
  { value: 'api-config', label: 'API config', group: 'Account' },
  { value: 'risk-limits', label: 'Risk limits', group: 'Risk' },
  { value: 'position-management', label: 'Position management', group: 'Risk' },
  { value: 'autonomous', label: 'Autonomous', group: 'System' },
  { value: 'alpha-edge', label: 'Alpha Edge', group: 'System' },
  { value: 'live-trading', label: 'Live trading', group: 'System' },
  { value: 'alerts', label: 'Alerts', group: 'Notifications' },
  { value: 'users', label: 'Users', group: 'Admin' },
  { value: 'shortcuts', label: 'Shortcuts', group: 'Reference' },
]

export function Settings() {
  return (
    <Routes>
      <Route index element={<Navigate to="/settings/trading-mode" replace />} />
      <Route path=":tab/*" element={<SettingsShell />} />
    </Routes>
  )
}

function SettingsShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const parts = location.pathname.split('/').filter(Boolean)
  const rawTab = parts[1] || 'trading-mode'
  const current: TabValue =
    (TABS.find((t) => t.value === rawTab)?.value as TabValue) ?? 'trading-mode'

  const description = TABS.find((t) => t.value === current)?.label ?? 'Settings'

  const leftPanel = (
    <nav
      className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto py-3 px-1.5 space-y-3"
      aria-label="Settings sections"
    >
      {groupedTabs().map((group) => (
        <div key={group.name} className="space-y-0.5">
          <div className="px-2.5 text-[9px] uppercase tracking-wider text-[var(--text-3)]">
            {group.name}
          </div>
          {group.items.map((t) => (
            <button
              key={t.value}
              type="button"
              onClick={() => navigate(`/settings/${t.value}`)}
              className={cn(
                'w-full text-left px-2.5 py-1.5 rounded-[3px] text-[12px] transition-colors',
                t.value === current
                  ? 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)] text-[var(--accent-primary)] font-medium'
                  : 'text-[var(--text-1)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
              )}
              aria-current={t.value === current ? 'page' : undefined}
            >
              {t.label}
            </button>
          ))}
        </div>
      ))}
    </nav>
  )

  const rightPanel = (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-4 py-4">
      {current === 'trading-mode' ? (
        <TradingModeTab />
      ) : current === 'api-config' ? (
        <ApiConfigTab />
      ) : current === 'risk-limits' ? (
        <RiskLimitsTab />
      ) : current === 'position-management' ? (
        <PositionManagementTab />
      ) : current === 'autonomous' ? (
        <AutonomousTab />
      ) : current === 'alpha-edge' ? (
        <AlphaEdgeSettingsTab />
      ) : current === 'alerts' ? (
        <AlertsSettingsTab />
      ) : current === 'live-trading' ? (
        <LiveTradingSettingsTab />
      ) : current === 'users' ? (
        <UsersTab />
      ) : (
        <ShortcutsTab />
      )}
    </div>
  )

  return (
    <PageTemplate title="Settings" description={description}>
      <ResizablePanelLayout
        layoutId="settings"
        panels={[
          {
            id: 'settings-left',
            defaultSize: 18,
            minSize: 14,
            maxSize: 28,
            content: leftPanel,
          },
          {
            id: 'settings-right',
            defaultSize: 82,
            minSize: 60,
            content: rightPanel,
          },
        ]}
      />
    </PageTemplate>
  )
}

function groupedTabs() {
  const groups = new Map<string, typeof TABS>()
  for (const t of TABS) {
    const g = t.group ?? 'Other'
    const list = (groups.get(g) ?? []) as typeof TABS
    list.push(t)
    groups.set(g, list)
  }
  return Array.from(groups.entries()).map(([name, items]) => ({ name, items }))
}
