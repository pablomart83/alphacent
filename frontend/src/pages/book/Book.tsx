import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { PageTemplate } from '@/components/layout'
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives'
import { useTradingMode } from '@/stores'
import { PositionsTab } from './positions/PositionsTab'
import { OrdersTab } from './orders/OrdersTab'
import { ExecutionTab } from './execution/ExecutionTab'
import { LiveTab } from './live/LiveTab'
import { PositionDetailPage } from './PositionDetailPage'

/**
 * Book surface — /book.
 *
 * Tabs: Positions · Orders · Execution · Live. All live as of Sprint 4.
 */

const TABS = [
  { value: 'positions', label: 'Positions' },
  { value: 'orders', label: 'Orders' },
  { value: 'execution', label: 'Execution' },
  { value: 'live', label: 'Live' },
] as const

type TabValue = (typeof TABS)[number]['value']

export function Book() {
  return (
    <Routes>
      <Route path="position/:symbol" element={<PositionDetailPage />} />
      <Route index element={<Navigate to="/book/positions" replace />} />
      <Route path=":tab/*" element={<BookShell />} />
    </Routes>
  )
}

function BookShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)

  const parts = location.pathname.split('/').filter(Boolean)
  const rawTab = parts[1] || 'positions'
  const current: TabValue =
    TABS.find((t) => t.value === rawTab)?.value ?? 'positions'

  const tabDescription =
    current === 'positions'
      ? `Positions · ${mode}`
      : current === 'orders'
        ? `Orders · ${mode}`
        : current === 'execution'
          ? `Execution · ${mode}`
          : 'Live trading'

  return (
    <PageTemplate title="Book" description={tabDescription}>
      <div className="flex flex-col h-full min-h-0">
        <Tabs
          value={current}
          onValueChange={(v) => navigate(`/book/${v}`)}
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
            {current === 'positions' ? (
              <PositionsTab />
            ) : current === 'orders' ? (
              <OrdersTab />
            ) : current === 'execution' ? (
              <ExecutionTab />
            ) : (
              <LiveTab />
            )}
          </div>
        </Tabs>
      </div>
    </PageTemplate>
  )
}
