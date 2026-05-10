import { useMemo } from 'react'
import { ResizablePanelLayout } from '@/components/layout'
import { useAutonomousStatus } from '@/pages/command/useCommandData'
import {
  useAutonomousCycles,
  useSystemStatus,
} from '../useStrategiesData'
import { SystemStateControl } from './SystemStateControl'
import { SchedulerPanel } from './SchedulerPanel'
import { ManualCycleTrigger } from './ManualCycleTrigger'
import { CyclePipelineVisual } from './CyclePipelineVisual'
import { SignalFunnel } from './SignalFunnel'
import { CycleIntelligencePanel } from './CycleIntelligencePanel'
import { CycleHistoryList } from './CycleHistoryList'
import { LiveStream } from './LiveStream'

/**
 * Cycle tab — /strategies/cycle.
 *
 * 30/40/30 split per spec §3B:
 *   Left   (30%): Scheduler + Controls — SystemStateControl, SchedulerPanel,
 *                 ManualCycleTrigger
 *   Middle (40%): Pipeline + Funnel — CyclePipelineVisual (hero),
 *                 CycleIntelligencePanel, SignalFunnel, CycleHistoryList
 *   Right  (30%): LiveStream — WS-fed rolling 100-event feed
 */

export function CycleTab() {
  const cyclesQuery = useAutonomousCycles(30)
  const statusQuery = useSystemStatus()
  const autonomousQuery = useAutonomousStatus()

  const { lastCycle, isRunning } = useMemo(() => {
    const rows = cyclesQuery.data?.data ?? []
    if (rows.length === 0) return { lastCycle: null, isRunning: false }
    const running = rows.find((r) => r.status?.toLowerCase() === 'running')
    if (running) return { lastCycle: running, isRunning: true }
    const completed = rows.find((r) => r.status?.toLowerCase() === 'completed') ?? rows[0]
    return { lastCycle: completed, isRunning: false }
  }, [cyclesQuery.data])

  return (
    <ResizablePanelLayout
      layoutId="strategies.cycle"
      panels={[
        {
          id: 'cycle-left',
          defaultSize: 30,
          minSize: 22,
          maxSize: 42,
          content: (
            <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto">
              <SystemStateControl />
              <SchedulerPanel />
              <ManualCycleTrigger />
            </div>
          ),
        },
        {
          id: 'cycle-main',
          defaultSize: 40,
          minSize: 30,
          content: (
            <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto">
              <CyclePipelineVisual
                lastCycle={lastCycle}
                isRunning={isRunning || statusQuery.data?.state === 'ACTIVE'}
              />
              <CycleIntelligencePanel
                lastCycle={lastCycle}
                regime={autonomousQuery.data?.market_regime}
                regimeConfidence={autonomousQuery.data?.market_confidence}
                loading={cyclesQuery.isLoading}
              />
              <SignalFunnel />
              <CycleHistoryList limit={30} />
            </div>
          ),
        },
        {
          id: 'cycle-stream',
          defaultSize: 30,
          minSize: 22,
          maxSize: 42,
          content: (
            <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">
              <LiveStream />
            </div>
          ),
        },
      ]}
    />
  )
}
