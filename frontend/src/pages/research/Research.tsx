import { useCallback, useEffect, useMemo } from 'react'
import { Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { PageTemplate } from '@/components/layout'
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives'
import { useResearchStore } from '@/stores'
import type { ResearchPeriod, ResearchInterval } from '@/stores'
import { useTradingMode } from '@/stores'
import { PerformanceTab } from './performance/PerformanceTab'
import { AttributionTab } from './attribution/AttributionTab'
import { TradesTab } from './trades/TradesTab'
import { RegimeTab } from './regime/RegimeTab'
import { AlphaEdgeTab } from './alpha-edge/AlphaEdgeTab'
import { TearSheetTab } from './tear-sheet/TearSheetTab'
import { StressTab } from './stress/StressTab'
import { JournalTab } from './journal/JournalTab'

/**
 * Research surface — /research.
 *
 * Tabs: Performance · Attribution · Trades · Regime · Alpha Edge ·
 *       Tear Sheet · Stress · Journal.
 *
 * The full-width content area uses a period + interval segmented control
 * persisted in Zustand so a CIO's selection survives tab switches.
 */

type TabValue =
  | 'performance'
  | 'attribution'
  | 'trades'
  | 'regime'
  | 'alpha-edge'
  | 'tear-sheet'
  | 'stress'
  | 'journal'

const TABS: Array<{ value: TabValue; label: string }> = [
  { value: 'performance', label: 'Performance' },
  { value: 'attribution', label: 'Attribution' },
  { value: 'trades', label: 'Trades' },
  { value: 'regime', label: 'Regime' },
  { value: 'alpha-edge', label: 'Alpha Edge' },
  { value: 'tear-sheet', label: 'Tear Sheet' },
  { value: 'stress', label: 'Stress' },
  { value: 'journal', label: 'Journal' },
]

const PERIODS: ResearchPeriod[] = ['1W', '1M', '3M', '6M', '1Y', 'ALL']
const INTERVALS: ResearchInterval[] = ['1d', '4h', '1h']
const INTERVAL_TABS: Array<TabValue> = ['performance']

export function Research() {
  return (
    <Routes>
      <Route index element={<Navigate to="/research/performance" replace />} />
      <Route path=":tab/*" element={<ResearchShell />} />
    </Routes>
  )
}

function ResearchShell() {
  const location = useLocation()
  const navigate = useNavigate()
  const mode = useTradingMode((s) => s.mode)
  const period = useResearchStore((s) => s.period)
  const interval = useResearchStore((s) => s.interval)
  const setPeriod = useResearchStore((s) => s.setPeriod)
  const setInterval = useResearchStore((s) => s.setInterval)

  const parts = location.pathname.split('/').filter(Boolean)
  const rawTab = parts[1] || 'performance'
  const current: TabValue =
    (TABS.find((t) => t.value === rawTab)?.value as TabValue) ?? 'performance'
  const showInterval = INTERVAL_TABS.includes(current)

  const description = useMemo(() => {
    const tab = TABS.find((t) => t.value === current)?.label ?? 'Performance'
    return `${tab} · ${mode} · ${period}`
  }, [current, mode, period])

  // Tab-to-number shortcuts: 1..8 jump between tabs when focus is outside inputs.
  const jumpToIndex = useCallback(
    (idx: number) => {
      const t = TABS[idx]
      if (t) navigate(`/research/${t.value}`)
    },
    [navigate],
  )

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null
      const inField =
        target &&
        (target.tagName === 'INPUT' ||
          target.tagName === 'TEXTAREA' ||
          target.isContentEditable)
      if (inField || e.metaKey || e.ctrlKey || e.altKey) return
      const n = Number(e.key)
      if (Number.isInteger(n) && n >= 1 && n <= TABS.length) {
        e.preventDefault()
        jumpToIndex(n - 1)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [jumpToIndex])

  const actions = (
    <div className="flex items-center gap-2">
      <SegmentedBar
        options={PERIODS}
        value={period}
        onChange={(v) => setPeriod(v as ResearchPeriod)}
      />
      {showInterval && (
        <SegmentedBar
          options={INTERVALS}
          value={interval}
          onChange={(v) => setInterval(v as ResearchInterval)}
        />
      )}
    </div>
  )

  return (
    <PageTemplate title="Research" description={description} actions={actions}>
      <div className="flex flex-col h-full min-h-0">
        <Tabs
          value={current}
          onValueChange={(v) => navigate(`/research/${v}`)}
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
            {current === 'performance' ? (
              <PerformanceTab />
            ) : current === 'attribution' ? (
              <AttributionTab />
            ) : current === 'trades' ? (
              <TradesTab />
            ) : current === 'regime' ? (
              <RegimeTab />
            ) : current === 'alpha-edge' ? (
              <AlphaEdgeTab />
            ) : current === 'tear-sheet' ? (
              <TearSheetTab />
            ) : current === 'stress' ? (
              <StressTab />
            ) : (
              <JournalTab />
            )}
          </div>
        </Tabs>
      </div>
    </PageTemplate>
  )
}

function SegmentedBar<T extends string>({
  options,
  value,
  onChange,
}: {
  options: readonly T[]
  value: T
  onChange: (v: T) => void
}) {
  return (
    <div className="flex items-center rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)]">
      {options.map((opt) => (
        <button
          key={opt}
          type="button"
          onClick={() => onChange(opt)}
          className={
            'h-6 px-2 text-[10px] font-medium uppercase tracking-wider transition-colors ' +
            (value === opt
              ? 'bg-[color-mix(in_oklab,var(--accent-primary)_15%,transparent)] text-[var(--accent-primary)]'
              : 'text-[var(--text-3)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]')
          }
        >
          {opt}
        </button>
      ))}
    </div>
  )
}
