import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Hammer } from 'lucide-react'
import { PageTemplate } from '@/components/layout'
import { Tabs, TabsList, TabsTrigger, EmptyState } from '@/components/primitives'
import { useTradingMode } from '@/stores'
import { PositionsTab } from './positions/PositionsTab'
import { OrdersTab } from './orders/OrdersTab'
import { ExecutionTab } from './execution/ExecutionTab'
import { PositionDetailPage } from './PositionDetailPage'

/**
 * Book surface — /book.
 *
 * Tabs: Positions · Orders · Execution · Live.
 * Positions, Orders, Execution are live. Live lands in Sprint 4.
 */

const TABS = [
  { value: 'positions', label: 'Positions', sprint: 2 },
  { value: 'orders', label: 'Orders', sprint: 3 },
  { value: 'execution', label: 'Execution', sprint: 3 },
  { value: 'live', label: 'Live', sprint: 4 },
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
          : `Live · Sprint 4`

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
              <div className="h-full flex items-center justify-center">
                <EmptyState
                  icon={Hammer}
                  title={`${current[0].toUpperCase()}${current.slice(1)} — coming in Sprint ${TABS.find((t) => t.value === current)?.sprint}`}
                  description="Positions, Orders, and Execution are live. Live tab lands in Sprint 4."
                />
              </div>
            )}
          </div>
        </Tabs>
      </div>
    </PageTemplate>
  )
}
