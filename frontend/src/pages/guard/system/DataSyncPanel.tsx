import { toast } from 'sonner'
import { PlayCircle, Zap, Database, Newspaper } from 'lucide-react'
import { Button, Skeleton } from '@/components/primitives'
import { SectionLabel } from '@/components/layout'
import { classifyError } from '@/lib/errors'
import { cn, formatAge, formatNumber, formatTimestamp } from '@/lib/utils'
import {
  useFmpCacheStatus,
  useNewsSentimentStatus,
  useTriggerFmpWarm,
  useTriggerFullSync,
  useTriggerNewsSentiment,
  useTriggerQuickUpdate,
  type DataSyncStatusPayload,
} from '../useGuardData'

interface DataSyncPanelProps {
  sync: DataSyncStatusPayload | null | undefined
  loading?: boolean
}

/**
 * DataSyncPanel — full-price sync + quick-update status, manual triggers for
 * each background sync (full, quick, FMP warm, news sentiment), and the last
 * 50 sync log lines when a sync is running.
 */
export function DataSyncPanel({ sync, loading }: DataSyncPanelProps) {
  const fmp = useFmpCacheStatus()
  const news = useNewsSentimentStatus()
  const triggerFull = useTriggerFullSync()
  const triggerQuick = useTriggerQuickUpdate()
  const triggerFmp = useTriggerFmpWarm()
  const triggerNews = useTriggerNewsSentiment()

  const fire = async (
    label: string,
    mutation: ReturnType<typeof useTriggerFullSync>,
  ) => {
    try {
      const res = await mutation.mutateAsync()
      toast.success(`${label}: ${res.message}`)
    } catch (err) {
      const info = classifyError(err, label.toLowerCase())
      toast.error(info.title, { description: info.message })
    }
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Data sync · manual triggers</SectionLabel>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
        <StatusCard
          title="Full price sync"
          running={!!sync?.sync_running}
          elapsed={sync?.sync_elapsed_s ?? null}
          lastRun={sync?.last_sync_at ?? null}
          lastDuration={sync?.last_sync_duration_s ?? null}
          success={sync?.last_sync_success}
          intervalLabel={sync ? `every ${Math.round((sync.sync_interval_s || 0) / 60)}m` : undefined}
          loading={loading}
          button={
            <Button
              size="sm"
              variant="primary"
              onClick={() => void fire('Full sync', triggerFull)}
              loading={triggerFull.isPending}
              className="gap-1.5"
            >
              <PlayCircle className="h-3.5 w-3.5" />
              Run full sync
            </Button>
          }
        />
        <StatusCard
          title="Quick update"
          running={false}
          elapsed={null}
          lastRun={sync?.quick_update?.last_run ?? null}
          lastDuration={sync?.quick_update?.duration_s ?? null}
          success={sync?.quick_update?.errors === 0}
          intervalLabel="every 10m"
          symbolsUpdated={sync?.quick_update?.symbols_updated ?? null}
          loading={loading}
          button={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void fire('Quick update', triggerQuick)}
              loading={triggerQuick.isPending}
              className="gap-1.5"
            >
              <Zap className="h-3.5 w-3.5" />
              Quick update
            </Button>
          }
        />
        <StatusCard
          title="FMP cache warm"
          running={!!fmp.data?.running}
          elapsed={null}
          lastRun={fmp.data?.last_warm_at ?? null}
          lastDuration={null}
          success={typeof fmp.data?.coverage_pct === 'number' ? fmp.data.coverage_pct >= 95 : undefined}
          intervalLabel={
            typeof fmp.data?.coverage_pct === 'number'
              ? `${fmp.data.coverage_pct.toFixed(0)}% coverage`
              : undefined
          }
          loading={fmp.isLoading}
          button={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void fire('FMP warm', triggerFmp)}
              loading={triggerFmp.isPending}
              className="gap-1.5"
            >
              <Database className="h-3.5 w-3.5" />
              Warm FMP cache
            </Button>
          }
        />
        <StatusCard
          title="News sentiment"
          running={!!news.data?.running}
          elapsed={null}
          lastRun={news.data?.last_run ?? null}
          lastDuration={null}
          success={typeof news.data?.coverage_pct === 'number' ? news.data.coverage_pct >= 70 : undefined}
          intervalLabel={
            typeof news.data?.coverage_pct === 'number'
              ? `${news.data.coverage_pct.toFixed(0)}% covered`
              : undefined
          }
          loading={news.isLoading}
          button={
            <Button
              size="sm"
              variant="secondary"
              onClick={() => void fire('News sentiment', triggerNews)}
              loading={triggerNews.isPending}
              className="gap-1.5"
            >
              <Newspaper className="h-3.5 w-3.5" />
              Sync sentiment
            </Button>
          }
        />
      </div>

      {sync?.sync_logs && sync.sync_logs.length > 0 && (
        <div className="mt-1">
          <SectionLabel>Sync log · last 50 lines</SectionLabel>
          <pre
            className={cn(
              'mono text-[9px] leading-snug text-[var(--text-2)]',
              'rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-0)]',
              'p-2 max-h-[180px] overflow-auto',
            )}
          >
            {sync.sync_logs.join('\n')}
          </pre>
        </div>
      )}
    </section>
  )
}

interface StatusCardProps {
  title: string
  running: boolean
  elapsed: number | null
  lastRun?: string | null
  lastDuration?: number | null
  success?: boolean
  intervalLabel?: string
  symbolsUpdated?: number | null
  loading?: boolean
  button: React.ReactNode
}

function StatusCard({
  title,
  running,
  elapsed,
  lastRun,
  lastDuration,
  success,
  intervalLabel,
  symbolsUpdated,
  loading,
  button,
}: StatusCardProps) {
  return (
    <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] p-2 space-y-1.5">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[11px] font-semibold text-[var(--text-0)] uppercase tracking-wider">
          {title}
        </span>
        <span
          className={cn(
            'inline-flex items-center gap-1 px-1.5 h-[16px] rounded-[3px] text-[9px] font-semibold uppercase tracking-wider',
            running && 'animate-pulse',
          )}
          style={{
            backgroundColor: `color-mix(in oklab, ${
              running
                ? 'var(--accent-primary)'
                : success === false
                  ? 'var(--pnl-down)'
                  : success
                    ? 'var(--pnl-up)'
                    : 'var(--text-3)'
            } 15%, transparent)`,
            color: running
              ? 'var(--accent-primary)'
              : success === false
                ? 'var(--pnl-down)'
                : success
                  ? 'var(--pnl-up)'
                  : 'var(--text-3)',
          }}
        >
          {running ? 'Running' : success === false ? 'Failed' : success ? 'OK' : 'Idle'}
        </span>
      </div>

      {loading ? (
        <Skeleton className="h-10 w-full" />
      ) : (
        <div className="text-[10px] text-[var(--text-3)] space-y-0.5">
          {running ? (
            <div>
              Elapsed <span className="mono tabular-nums text-[var(--text-1)]">{elapsed?.toFixed(0) ?? '—'}s</span>
            </div>
          ) : (
            <>
              <div>
                Last run{' '}
                <span className="mono tabular-nums text-[var(--text-1)]">
                  {formatAge(lastRun) || '—'}
                </span>
                <span className="ml-1 text-[9px]">
                  {formatTimestamp(lastRun, 'short') || ''}
                </span>
              </div>
              {typeof lastDuration === 'number' && (
                <div>
                  Duration{' '}
                  <span className="mono tabular-nums text-[var(--text-1)]">
                    {lastDuration.toFixed(2)}s
                  </span>
                </div>
              )}
              {typeof symbolsUpdated === 'number' && (
                <div>
                  Symbols updated{' '}
                  <span className="mono tabular-nums text-[var(--text-1)]">
                    {formatNumber(symbolsUpdated)}
                  </span>
                </div>
              )}
              {intervalLabel && (
                <div className="text-[9px] uppercase tracking-wider">{intervalLabel}</div>
              )}
            </>
          )}
        </div>
      )}

      <div>{button}</div>
    </div>
  )
}
