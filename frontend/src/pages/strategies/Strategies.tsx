import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Hammer } from 'lucide-react'
import { PageTemplate } from '@/components/layout'
import { Tabs, TabsList, TabsTrigger, EmptyState } from '@/components/primitives'
import { useTradingMode } from '@/stores'
import { LibraryTab } from './library/LibraryTab'
import { CycleTab } from './cycle/CycleTab'

/**
 * Strategies surface — /strategies.
 *
 * Tabs: Library · Cycle · Templates · Symbols · Graduation · Lab.
 * Library (Sprint 5) and Cycle (Sprint 6) are live. Templates / Symbols /
 * Graduation / Lab render scoped ComingSoon cards with their sprint numbers.
 */

type TabValue = 'library' | 'cycle' | 'templates' | 'symbols' | 'graduation' | 'lab'

const TABS: Array<{ value: TabValue; label: string; sprint?: number }> = [
  { value: 'library', label: 'Library' },
  { value: 'cycle', label: 'Cycle' },
  { value: 'templates', label: 'Templates', sprint: 7 },
  { value: 'symbols', label: 'Symbols', sprint: 7 },
  { value: 'graduation', label: 'Graduation', sprint: 7 },
  { value: 'lab', label: 'Lab', sprint: 7 },
]

export function Strategies() {
  return (
    <Routes>
      <Route index element={<Navigate to="/strategies/library" replace />} />
      <Route path=":tab/*" element={<StrategiesShell />} />
    </Routes>
  )
}

function StrategiesShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)

  const parts = location.pathname.split('/').filter(Boolean)
  const rawTab = parts[1] || 'library'
  const current: TabValue =
    (TABS.find((t) => t.value === rawTab)?.value as TabValue) ?? 'library'

  const description =
    current === 'library'
      ? `Library · ${mode}`
      : current === 'cycle'
        ? 'Autonomous cycle · DEMO'
        : current === 'templates'
          ? 'Template library'
          : current === 'symbols'
            ? 'Symbol analytics'
            : current === 'graduation'
              ? 'Graduation queue'
              : 'Research lab'

  return (
    <PageTemplate title="Strategies" description={description}>
      <div className="flex flex-col h-full min-h-0">
        <Tabs
          value={current}
          onValueChange={(v) => navigate(`/strategies/${v}`)}
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
            {current === 'library' ? (
              <LibraryTab />
            ) : current === 'cycle' ? (
              <CycleTab />
            ) : (
              <ComingSoonCard
                tab={current}
                sprint={TABS.find((t) => t.value === current)?.sprint ?? 7}
              />
            )}
          </div>
        </Tabs>
      </div>
    </PageTemplate>
  )
}

function ComingSoonCard({ tab, sprint }: { tab: string; sprint: number }) {
  const copy: Record<string, string> = {
    templates:
      'Template grid + TemplateRankings leaderboard. Bulk toggle per template, direction filter. Ships with Sprint 7.',
    symbols:
      'Current vs Lifetime view of symbol usage. Historical proposals + trades per symbol. Ships with Sprint 7.',
    graduation:
      'CIO promotion workflow — graduation queue, flagship GraduationCard, active live authorizations, post-retirement re-graduation. Ships with Sprint 7.',
    lab:
      'BacktestRunner, VibeCodeTranslator, GenerateStrategy, BootstrapRunner. Ships with Sprint 7.',
  }
  return (
    <div className="flex h-full items-center justify-center bg-[var(--bg-0)]">
      <EmptyState
        icon={Hammer}
        title={`${tab.charAt(0).toUpperCase() + tab.slice(1)} — Sprint ${sprint}`}
        description={copy[tab] ?? `Lands in Sprint ${sprint}.`}
      />
    </div>
  )
}
