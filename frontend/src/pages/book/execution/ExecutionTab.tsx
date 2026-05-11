import { useState } from 'react'
import { Tabs, TabsList, TabsTrigger } from '@/components/primitives'
import { SlippageTab } from './SlippageTab'
import { TCATab } from './TCATab'
import { PaperLiveAnalyticsTab } from './PaperLiveAnalyticsTab'
import { ExecutionSummaryStrip } from './ExecutionSummaryStrip'

type SubTab = 'slippage' | 'tca' | 'analytics'

const SUB_TABS: Array<{ value: SubTab; label: string }> = [
  { value: 'slippage', label: 'Slippage' },
  { value: 'tca', label: 'TCA' },
  { value: 'analytics', label: 'Analytics' },
]

/**
 * Execution tab — summary strip + three sub-tabs:
 *   Slippage  — client-side execution quality
 *   TCA       — server-side transaction cost analysis
 *   Analytics — strategy attribution + conviction calibration
 */
export function ExecutionTab() {
  const [sub, setSub] = useState<SubTab>('slippage')

  return (
    <div className="flex flex-col h-full min-h-0">
      <ExecutionSummaryStrip />
      <Tabs
        value={sub}
        onValueChange={(v) => setSub(v as SubTab)}
        className="flex flex-col flex-1 min-h-0"
      >
        <TabsList className="shrink-0 px-2 pt-1 border-b border-[var(--border-subtle)] bg-[var(--bg-0)]">
          {SUB_TABS.map((t) => (
            <TabsTrigger key={t.value} value={t.value}>
              {t.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <div className="flex-1 min-h-0">
          {sub === 'slippage' ? (
            <SlippageTab />
          ) : sub === 'tca' ? (
            <TCATab />
          ) : (
            <PaperLiveAnalyticsTab />
          )}
        </div>
      </Tabs>
    </div>
  )
}
