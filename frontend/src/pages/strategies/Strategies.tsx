import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { PageTemplate } from '@/components/layout'
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives'
import { useTradingMode } from '@/stores'
import { LibraryTab } from './library/LibraryTab'
import { CycleTab } from './cycle/CycleTab'
import { TemplatesTab } from './templates/TemplatesTab'
import { SymbolsTab } from './symbols/SymbolsTab'
import { GraduationTab } from './graduation/GraduationTab'
import { LabTab } from './lab/LabTab'

/**
 * Strategies surface — /strategies.
 *
 * Tabs: Library · Cycle · Templates · Symbols · Graduation · Lab.
 */

type TabValue = 'library' | 'cycle' | 'templates' | 'symbols' | 'graduation' | 'lab'

const TABS: Array<{ value: TabValue; label: string }> = [
  { value: 'library', label: 'Library' },
  { value: 'cycle', label: 'Cycle' },
  { value: 'templates', label: 'Templates' },
  { value: 'symbols', label: 'Symbols' },
  { value: 'graduation', label: 'Graduation' },
  { value: 'lab', label: 'Lab' },
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
              ? 'CIO promotion workflow'
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
            ) : current === 'templates' ? (
              <TemplatesTab />
            ) : current === 'symbols' ? (
              <SymbolsTab />
            ) : current === 'graduation' ? (
              <GraduationTab />
            ) : (
              <LabTab />
            )}
          </div>
        </Tabs>
      </div>
    </PageTemplate>
  )
}
