import { ErrorState } from '@/components/primitives'
import { classifyError } from '@/lib/errors'
import {
  useDataQuality,
  useDataSyncStatus,
  useMonitoringStatus,
  useSystemHealth,
} from '../useGuardData'
import { HealthTiles } from './HealthTiles'
import { WebSocketHealthCard } from './WebSocketHealthCard'
import { MonitoringServiceCard } from './MonitoringServiceCard'
import { BackgroundThreadsTable } from './BackgroundThreadsTable'
import { DataSyncPanel } from './DataSyncPanel'
import { DbStatsCard } from './DbStatsCard'
import { DataQualityTable } from './DataQualityTable'
import { EventTimeline24h } from './EventTimeline24h'

/**
 * SystemTab — merges the old System Health + Data Management surfaces per
 * spec §3B. Single scrollable column that fits the 70% right panel and
 * never forces horizontal scrolling at desktop widths.
 */
export function SystemTab() {
  const health = useSystemHealth()
  const monitoring = useMonitoringStatus()
  const sync = useDataSyncStatus()
  const quality = useDataQuality()

  if (health.isError) {
    const info = classifyError(health.error, 'system health')
    return (
      <ErrorState
        title="Couldn't load system health"
        message={info.message}
        onRetry={() => health.refetch()}
      />
    )
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)] overflow-auto px-3 py-3 space-y-5">
      <HealthTiles health={health.data} loading={health.isLoading} />
      <WebSocketHealthCard />
      <MonitoringServiceCard
        health={health.data}
        monitoring={monitoring.data}
        loading={monitoring.isLoading}
      />
      <BackgroundThreadsTable health={health.data} loading={health.isLoading} />
      <DataSyncPanel sync={sync.data} loading={sync.isLoading} />
      <DbStatsCard sync={sync.data} loading={sync.isLoading} />
      <DataQualityTable entries={quality.data?.entries} loading={quality.isLoading} />
      <EventTimeline24h health={health.data} loading={health.isLoading} />
    </div>
  )
}
