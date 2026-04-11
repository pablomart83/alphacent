import { type FC, useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { DashboardLayout } from '../components/DashboardLayout';
import { RefreshButton } from '../components/ui/RefreshButton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { usePolling } from '../hooks/usePolling';
import { apiClient } from '../services/api';
import { classifyError } from '../lib/errors';
import { utcToLocal } from '../lib/date-utils';
import { toast } from 'sonner';

interface SyncStatus {
  last_sync_at: string | null;
  last_sync_success: boolean;
  last_sync_duration_s: number | null;
  last_sync_stats: Record<string, unknown> | null;
  sync_running: boolean;
  sync_interval_s: number;
  db_stats: {
    total_bars: number;
    by_interval: Record<string, number>;
    unique_symbols: number;
    latest_bar: string | null;
    oldest_bar: string | null;
    recent_1h_symbols: Array<{ symbol: string; latest: string }>;
  } | null;
  sync_logs: string[] | null;
  sync_elapsed_s: number | null;
  quick_update: {
    updated: number;
    errors: number;
    symbols_checked: number;
    elapsed_s: number;
    timestamp: string;
  } | null;
}

interface DataManagementNewProps {
  onLogout: () => void;
}

export const DataManagementNew: FC<DataManagementNewProps> = ({ onLogout }) => {
  const [status, setStatus] = useState<SyncStatus | null>(null);
  const [monitoringStatus, setMonitoringStatus] = useState<Record<string, any> | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [quickUpdating, setQuickUpdating] = useState(false);
  const [_error, setError] = useState<ReturnType<typeof classifyError> | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  // Data quality state
  const [dataQuality, setDataQuality] = useState<any[]>([]);
  const [dqSortKey, setDqSortKey] = useState<string>('quality_score');
  const [dqSortAsc, setDqSortAsc] = useState(false);
  const [dqFilterClass, setDqFilterClass] = useState<string>('all');
  const [dqFilterScore, setDqFilterScore] = useState<string>('all');

  const fetchStatus = useCallback(async () => {
    try {
      setError(null);
      const [data, monData, dqData] = await Promise.all([
        apiClient.getDataSyncStatus() as Promise<SyncStatus>,
        apiClient.getMonitoringStatus().catch(() => null),
        apiClient.getDataQuality().catch(() => []),
      ]);
      setStatus(data);
      if (monData) setMonitoringStatus(monData);
      if (dqData) setDataQuality(dqData);
      setLastFetchedAt(new Date());
      return data;
    } catch (err) {
      setError(classifyError(err, 'sync status'));
      toast.error('Failed to load sync status');
      return null;
    } finally {
      setLoading(false);
    }
  }, []);

  const startPolling = useCallback(() => {
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      const data = await fetchStatus();
      if (data && !data.sync_running) {
        if (pollRef.current) clearInterval(pollRef.current);
        pollRef.current = null;
        setSyncing(false);
        toast.success('Data sync completed');
      }
      // Auto-scroll log
      logEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }, 2000);
  }, [fetchStatus]);

  // Cleanup sync polling on unmount
  useEffect(() => {
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, []);

  // Polling for data refresh
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: async () => { await fetchStatus(); },
    intervalMs: 30000,
    enabled: true,
  });

  const handleTriggerSync = async () => {
    setSyncing(true);
    try {
      const result = await apiClient.triggerDataSync();
      if (result.success) {
        toast.success('Data sync started');
        startPolling();
      } else {
        toast.error(result.message);
        setSyncing(false);
      }
    } catch {
      toast.error('Failed to trigger sync');
      setSyncing(false);
    }
  };

  const handleTriggerQuickUpdate = async () => {
    setQuickUpdating(true);
    try {
      const result = await apiClient.triggerQuickUpdate();
      if (result.success) {
        toast.success('Quick price update started');
        // Poll for completion
        setTimeout(async () => {
          await fetchStatus();
          setQuickUpdating(false);
          toast.success('Quick price update completed');
        }, 8000);
      } else {
        toast.error(result.message);
        setQuickUpdating(false);
      }
    } catch {
      toast.error('Failed to trigger quick update');
      setQuickUpdating(false);
    }
  };

  const formatAge = (iso: string | null) => {
    if (!iso) return '—';
    const age = (Date.now() - utcToLocal(iso).getTime()) / 1000;
    if (age < 0) return 'just now';
    if (age < 60) return `${Math.round(age)}s ago`;
    if (age < 3600) return `${Math.round(age / 60)}m ago`;
    return `${(age / 3600).toFixed(1)}h ago`;
  };

  const formatDate = (iso: string | null) => {
    if (!iso) return 'Never';
    return utcToLocal(iso).toLocaleString();
  };

  const db = status?.db_stats;
  const stats = status?.last_sync_stats as Record<string, number> | null;
  const logs = status?.sync_logs ?? [];
  const isRunning = syncing || (status?.sync_running ?? false);

  // Data quality: sort + filter
  const assetClasses = useMemo(() => {
    const s = new Set(dataQuality.map((d: any) => d.asset_class).filter(Boolean));
    return Array.from(s).sort();
  }, [dataQuality]);

  const filteredDq = useMemo(() => {
    let items = [...dataQuality];
    if (dqFilterClass !== 'all') items = items.filter((d: any) => d.asset_class === dqFilterClass);
    if (dqFilterScore === 'green') items = items.filter((d: any) => d.quality_score > 80);
    else if (dqFilterScore === 'yellow') items = items.filter((d: any) => d.quality_score >= 60 && d.quality_score <= 80);
    else if (dqFilterScore === 'red') items = items.filter((d: any) => d.quality_score < 60);
    items.sort((a: any, b: any) => {
      const av = a[dqSortKey] ?? 0;
      const bv = b[dqSortKey] ?? 0;
      if (typeof av === 'string') return dqSortAsc ? av.localeCompare(bv) : bv.localeCompare(av);
      return dqSortAsc ? av - bv : bv - av;
    });
    return items;
  }, [dataQuality, dqFilterClass, dqFilterScore, dqSortKey, dqSortAsc]);

  const handleDqSort = (key: string) => {
    if (dqSortKey === key) setDqSortAsc(!dqSortAsc);
    else { setDqSortKey(key); setDqSortAsc(true); }
  };

  const scoreColor = (score: number) => {
    if (score > 80) return '#22c55e';
    if (score >= 60) return '#eab308';
    return '#ef4444';
  };

  return (
    <DashboardLayout onLogout={onLogout}>
      <div className="p-8 space-y-6 relative">
        <RefreshIndicator visible={pollingRefreshing} />

        {loading ? (
          <PageSkeleton />
        ) : (
        <>
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-mono" style={{ color: 'var(--color-text-primary)' }}>
              Data Management
            </h2>
            <div className="flex items-center gap-3 mt-1">
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                Market data sync, DB cache, and data freshness
              </p>
              <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
            </div>
          </div>
          <RefreshButton loading={loading} onClick={fetchStatus} label="Refresh" variant="outline" size="sm" />
        </div>

        {/* Stale Data Warning Banner */}
        {(() => {
          if (!db?.recent_1h_symbols || db.recent_1h_symbols.length === 0) return null;
          const staleSymbols = db.recent_1h_symbols.filter(s => {
            const ageMs = Date.now() - new Date(s.latest).getTime();
            return ageMs > 2 * 60 * 60 * 1000; // >2 hours
          });
          const totalSymbols = db.unique_symbols || db.recent_1h_symbols.length;
          const stalePercent = totalSymbols > 0 ? (staleSymbols.length / totalSymbols) * 100 : 0;
          if (stalePercent <= 10) return null;
          return (
            <div className="rounded-lg border p-4" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
              <div className="flex items-center gap-2">
                <span className="text-amber-400 text-lg">⚠</span>
                <div>
                  <p className="text-sm font-semibold text-amber-400">Stale Data Warning</p>
                  <p className="text-xs text-amber-400/80">
                    {staleSymbols.length} of {totalSymbols} symbols ({stalePercent.toFixed(0)}%) have stale hourly data (&gt;2h old). Consider running a sync.
                  </p>
                </div>
              </div>
            </div>
          );
        })()}

        {/* FMP API Usage — Prominent */}
        {monitoringStatus?.system?.fmp && (
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-3" style={{ color: 'var(--color-text-primary)' }}>FMP API Usage</h3>
            <div className="flex items-center gap-4">
              <div className="flex-1">
                <div className="flex justify-between text-sm mb-1">
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    {monitoringStatus.system.fmp.calls_today ?? 0} / {monitoringStatus.system.fmp.max_calls ?? '?'} calls today
                  </span>
                  <span className="font-mono" style={{ color: 'var(--color-text-primary)' }}>
                    {monitoringStatus.system.fmp.usage_percent ?? 0}%
                  </span>
                </div>
                <div className="w-full h-3 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, monitoringStatus.system.fmp.usage_percent ?? 0)}%`,
                      backgroundColor: (monitoringStatus.system.fmp.usage_percent ?? 0) > 80 ? '#ef4444' : (monitoringStatus.system.fmp.usage_percent ?? 0) > 50 ? '#f59e0b' : '#22c55e',
                    }}
                  />
                </div>
              </div>
              <div className="text-right">
                <div className="text-2xl font-mono font-bold" style={{ color: 'var(--color-text-primary)' }}>
                  {((monitoringStatus.system.fmp.max_calls ?? 0) - (monitoringStatus.system.fmp.calls_today ?? 0)).toLocaleString()}
                </div>
                <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>remaining</div>
              </div>
            </div>
            <div className="flex items-center gap-4 mt-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>
              <span>Status: <span className={monitoringStatus.system.fmp.status === 'healthy' ? 'text-green-400' : monitoringStatus.system.fmp.status === 'configured' ? 'text-blue-400' : 'text-red-400'}>{monitoringStatus.system.fmp.status}</span></span>
              <span>Cache: {monitoringStatus.system.fmp.cache_size ?? 0} entries</span>
            </div>
          </div>
        )}

        {/* Sync Status + Trigger */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-mono" style={{ color: 'var(--color-text-primary)' }}>Hourly Price Sync</h3>
            <button
              onClick={handleTriggerSync}
              disabled={isRunning}
              className="px-4 py-2 rounded-lg text-sm font-mono transition-all duration-200 disabled:opacity-50"
              style={{
                backgroundColor: isRunning ? 'var(--color-dark-bg)' : 'var(--color-accent-green)',
                color: isRunning ? 'var(--color-text-secondary)' : '#000',
              }}
            >
              {isRunning ? `⟳ Syncing${status?.sync_elapsed_s ? ` (${status.sync_elapsed_s}s)` : '...'}` : '▶ Run Sync Now'}
            </button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Status</p>
              <div className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full ${
                  isRunning ? 'bg-amber-400 animate-pulse' :
                  status?.last_sync_success ? 'bg-green-400' : 'bg-red-400'
                }`} />
                <span className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                  {isRunning ? 'Running' : status?.last_sync_success ? 'Healthy' : 'No sync yet'}
                </span>
              </div>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Last Sync</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                {formatAge(status?.last_sync_at ?? null)}
              </p>
              <p className="text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                {formatDate(status?.last_sync_at ?? null)}
              </p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Duration</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                {status?.last_sync_duration_s != null ? `${status.last_sync_duration_s}s` : '—'}
              </p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Interval</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                {status ? `${Math.round(status.sync_interval_s / 60)}min` : '—'}
              </p>
            </div>
          </div>

          {/* Last sync detailed stats */}
          {stats && typeof stats === 'object' && 'daily_fetched' in stats && (
            <div className="grid grid-cols-3 md:grid-cols-6 gap-3 mb-4">
              {[
                { label: '1d Fetched', value: stats.daily_fetched, color: 'text-green-400' },
                { label: '1d From DB', value: stats.daily_cached, color: 'text-blue-400' },
                { label: '1h Fetched', value: stats.hourly_fetched, color: 'text-green-400' },
                { label: '1h From DB', value: stats.hourly_cached, color: 'text-blue-400' },
                { label: 'In Memory', value: stats.memory_loaded, color: 'text-cyan-400' },
                { label: 'Weekend Skip', value: stats.weekend_skipped, color: 'text-gray-500' },
              ].map(({ label, value, color }) => (
                <div key={label} className="rounded-lg p-3 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className={`text-lg font-mono ${color}`}>{value ?? 0}</p>
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* 10-Min Quick Price Update */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-mono" style={{ color: 'var(--color-text-primary)' }}>
              10-Min Quick Price Update (eToro)
            </h3>
            <button
              onClick={handleTriggerQuickUpdate}
              disabled={quickUpdating}
              className="px-4 py-2 rounded-lg text-sm font-mono transition-all duration-200 disabled:opacity-50"
              style={{
                backgroundColor: quickUpdating ? 'var(--color-dark-bg)' : 'var(--color-accent-green)',
                color: quickUpdating ? 'var(--color-text-secondary)' : '#000',
              }}
            >
              {quickUpdating ? '⟳ Updating...' : '▶ Run Now'}
            </button>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Last Update</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                {status?.quick_update?.timestamp ? formatAge(status.quick_update.timestamp) : '—'}
              </p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Symbols Updated</p>
              <p className="text-xl font-mono text-green-400">{status?.quick_update?.updated ?? '—'}</p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Errors</p>
              <p className={`text-xl font-mono ${(status?.quick_update?.errors ?? 0) > 0 ? 'text-red-400' : 'text-gray-500'}`}>
                {status?.quick_update?.errors ?? '—'}
              </p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Duration</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                {status?.quick_update?.elapsed_s != null ? `${status.quick_update.elapsed_s}s` : '—'}
              </p>
            </div>
            <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
              <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Interval</p>
              <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>10min</p>
            </div>
          </div>
          <p className="text-xs mt-3" style={{ color: 'var(--color-text-secondary)' }}>
            Fetches live eToro quotes for active strategy symbols, updates in-memory cache, and runs signal check.
          </p>
        </div>

        {/* Data Quality Table (Req 19.1, 19.2, 19.6, 19.10) */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-mono" style={{ color: 'var(--color-text-primary)' }}>Data Quality</h3>
            <div className="flex items-center gap-2">
              <select
                value={dqFilterClass}
                onChange={(e) => setDqFilterClass(e.target.value)}
                className="text-xs font-mono rounded px-2 py-1 border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              >
                <option value="all">All Classes</option>
                {assetClasses.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select
                value={dqFilterScore}
                onChange={(e) => setDqFilterScore(e.target.value)}
                className="text-xs font-mono rounded px-2 py-1 border"
                style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
              >
                <option value="all">All Scores</option>
                <option value="green">Good (&gt;80)</option>
                <option value="yellow">Warning (60-80)</option>
                <option value="red">Critical (&lt;60)</option>
              </select>
            </div>
          </div>
          {filteredDq.length > 0 ? (
            <div className="overflow-x-auto max-h-[400px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead className="sticky top-0" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <tr style={{ color: 'var(--color-text-secondary)' }}>
                    {[
                      { key: 'symbol', label: 'Symbol' },
                      { key: 'asset_class', label: 'Class' },
                      { key: 'quality_score', label: 'Score' },
                      { key: 'last_price_update', label: 'Last Update' },
                      { key: 'data_source', label: 'Source' },
                      { key: 'active_issues', label: 'Issues' },
                      { key: 'staleness_seconds', label: 'Staleness' },
                    ].map((col) => (
                      <th
                        key={col.key}
                        className="text-left py-2 px-3 cursor-pointer hover:text-gray-300 text-xs font-mono"
                        onClick={() => handleDqSort(col.key)}
                      >
                        {col.label} {dqSortKey === col.key ? (dqSortAsc ? '↑' : '↓') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredDq.map((row: any) => (
                    <tr key={row.symbol} style={{ borderTop: '1px solid var(--color-dark-border)' }}>
                      <td className="py-2 px-3 font-mono" style={{ color: 'var(--color-text-primary)' }}>
                        {row.symbol}
                        {row.quality_score < 60 && <span className="ml-1 text-red-400 text-xs" title="Low quality score">⚠</span>}
                      </td>
                      <td className="py-2 px-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.asset_class || '—'}</td>
                      <td className="py-2 px-3 font-mono font-semibold" style={{ color: row.quality_score != null ? scoreColor(row.quality_score) : 'var(--color-text-secondary)' }}>
                        {row.quality_score != null ? row.quality_score : <span className="text-gray-500">Pending</span>}
                      </td>
                      <td className="py-2 px-3 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.last_price_update ? formatAge(row.last_price_update) : '—'}</td>
                      <td className="py-2 px-3 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.data_source || '—'}</td>
                      <td className="py-2 px-3 font-mono" style={{ color: (row.active_issues ?? 0) > 0 ? '#eab308' : 'var(--color-text-secondary)' }}>{row.active_issues ?? 0}</td>
                      <td className="py-2 px-3 font-mono text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                        {row.staleness_seconds != null ? (row.staleness_seconds < 3600 ? `${Math.round(row.staleness_seconds / 60)}m` : `${(row.staleness_seconds / 3600).toFixed(1)}h`) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
              {dataQuality.length === 0 ? 'Data quality report not available yet.' : 'No symbols match the current filters.'}
            </p>
          )}
        </div>

        {/* FMP Cache Status (Req 19.3) */}
        {monitoringStatus?.system?.fmp && (
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>FMP Cache Status</h3>
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Last Warm</p>
                <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                  {monitoringStatus.system.fmp.last_warm_time ? formatAge(monitoringStatus.system.fmp.last_warm_time) : '—'}
                </p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Symbols Warmed</p>
                <p className="text-xl font-mono text-blue-400">{monitoringStatus.system.fmp.cache_size ?? 0}</p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>API Calls Today</p>
                <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>{monitoringStatus.system.fmp.calls_today ?? 0}</p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Cache Hits</p>
                <p className="text-xl font-mono text-green-400">{monitoringStatus.system.fmp.cache_hits ?? '—'}</p>
              </div>
              <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Remaining Calls</p>
                <p className="text-xl font-mono" style={{ color: (monitoringStatus.system.fmp.max_calls - monitoringStatus.system.fmp.calls_today) < 50 ? '#ef4444' : 'var(--color-text-primary)' }}>
                  {((monitoringStatus.system.fmp.max_calls ?? 0) - (monitoringStatus.system.fmp.calls_today ?? 0)).toLocaleString()}
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Data Source Health (Req 19.4) */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Data Source Health</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {[
              { name: 'eToro', data: monitoringStatus?.system?.etoro },
              { name: 'Yahoo Finance', data: monitoringStatus?.system?.yahoo },
              { name: 'FMP', data: monitoringStatus?.system?.fmp },
              { name: 'FRED', data: monitoringStatus?.system?.fred },
            ].map(({ name, data }) => (
              <div key={name} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <div className="flex items-center gap-2 mb-2">
                  <div className={`w-2.5 h-2.5 rounded-full ${
                    data?.status === 'healthy' ? 'bg-green-400' :
                    data?.status === 'configured' ? 'bg-blue-400' :
                    data?.status === 'degraded' ? 'bg-amber-400' :
                    data?.status === 'disabled' || data?.status === 'no_api_key' ? 'bg-gray-500' :
                    data?.status === 'unknown' || !data ? 'bg-gray-600' :
                    data ? 'bg-red-400' : 'bg-gray-600'
                  }`} />
                  <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>{name}</p>
                </div>
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Status: <span className={
                    data?.status === 'healthy' ? 'text-green-400' :
                    data?.status === 'configured' ? 'text-blue-400' :
                    data?.status === 'degraded' ? 'text-amber-400' :
                    'text-gray-500'
                  }>{data?.status ?? 'unknown'}</span>
                </p>
                {data?.last_fetch_age && <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>Last fetch: {data.last_fetch_age}</p>}
                {data?.error_count != null && <p className="text-xs mt-0.5" style={{ color: data.error_count > 0 ? '#ef4444' : 'var(--color-text-secondary)' }}>Errors (1h): {data.error_count}</p>}
                {data?.avg_response_ms != null && <p className="text-xs mt-0.5 font-mono" style={{ color: 'var(--color-text-secondary)' }}>{data.avg_response_ms}ms avg</p>}
              </div>
            ))}
          </div>
        </div>

        {/* Price Sync Timeline (Req 19.5) */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Price Sync Timeline</h3>
          <div className="space-y-4">
            {/* Quick Update (10min) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>Quick Price Update (10min)</span>
                <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                  Last: {status?.quick_update?.timestamp ? formatAge(status.quick_update.timestamp) : '—'}
                </span>
              </div>
              <div className="w-full h-3 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <div
                  className="h-full rounded-full transition-all duration-1000"
                  style={{
                    width: quickUpdating ? '60%' : '100%',
                    backgroundColor: quickUpdating ? '#eab308' : '#22c55e',
                    animation: quickUpdating ? 'pulse 1.5s ease-in-out infinite' : 'none',
                  }}
                />
              </div>
              <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                <span>{status?.quick_update?.updated ?? 0} symbols • {status?.quick_update?.elapsed_s ?? 0}s</span>
                <span>Next: ~10min cycle</span>
              </div>
            </div>
            {/* Full Sync (55min) */}
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>Full Price Sync (55min)</span>
                <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                  Last: {status?.last_sync_at ? formatAge(status.last_sync_at) : '—'}
                </span>
              </div>
              <div className="w-full h-3 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <div
                  className="h-full rounded-full transition-all duration-1000"
                  style={{
                    width: isRunning ? `${Math.min(95, ((status?.sync_elapsed_s ?? 0) / (status?.last_sync_duration_s ?? 60)) * 100)}%` : '100%',
                    backgroundColor: isRunning ? '#3b82f6' : '#22c55e',
                    animation: isRunning ? 'pulse 1.5s ease-in-out infinite' : 'none',
                  }}
                />
              </div>
              <div className="flex justify-between text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                <span>{db?.unique_symbols ?? 0} symbols • {status?.last_sync_duration_s ?? 0}s</span>
                <span>Interval: {status ? `${Math.round(status.sync_interval_s / 60)}min` : '—'}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Historical Data Coverage Heatmap (Req 19.8, 19.9) */}
        {db?.recent_1h_symbols && db.recent_1h_symbols.length > 0 && (
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Historical Data Coverage</h3>
            <div className="overflow-x-auto">
              <div className="grid gap-0.5" style={{ gridTemplateColumns: `80px repeat(${Math.min(12, db.recent_1h_symbols.length)}, 1fr)` }}>
                {/* Header row */}
                <div className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>Symbol</div>
                {db.recent_1h_symbols.slice(0, 12).map((s: any) => (
                  <div key={`h-${s.symbol}`} className="text-[9px] font-mono text-center truncate" style={{ color: 'var(--color-text-secondary)' }}>
                    {s.symbol.slice(0, 5)}
                  </div>
                ))}
                {/* Data rows — show a simplified coverage view */}
                {['1h', '1d'].map((interval) => (
                  <>
                    <div key={interval} className="text-xs font-mono py-1" style={{ color: 'var(--color-text-secondary)' }}>{interval}</div>
                    {db.recent_1h_symbols.slice(0, 12).map((s: any) => {
                      const ageMs = Date.now() - new Date(s.latest).getTime();
                      const fresh = ageMs < 2 * 60 * 60 * 1000;
                      return (
                        <div
                          key={`${interval}-${s.symbol}`}
                          className="h-6 rounded-sm cursor-pointer"
                          style={{ backgroundColor: fresh ? 'rgba(34,197,94,0.3)' : 'rgba(239,68,68,0.3)' }}
                          title={`${s.symbol} (${interval}): ${fresh ? 'Fresh' : 'Stale'} — Last: ${new Date(s.latest).toLocaleString()}`}
                        />
                      );
                    })}
                  </>
                ))}
              </div>
              {db.recent_1h_symbols.length > 12 && (
                <p className="text-xs mt-2" style={{ color: 'var(--color-text-secondary)' }}>
                  Showing 12 of {db.recent_1h_symbols.length} symbols. Green = fresh, Red = stale/gap.
                </p>
              )}
            </div>
          </div>
        )}

        {/* Symbol Coverage — Stale Data */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Symbol Coverage</h3>
          {db?.recent_1h_symbols && db.recent_1h_symbols.length > 0 ? (() => {
            const now = Date.now();
            const staleHourly = db.recent_1h_symbols.filter(s => (now - new Date(s.latest).getTime()) > 2 * 60 * 60 * 1000);
            const totalSymbols = db.unique_symbols || db.recent_1h_symbols.length;
            return (
              <div className="space-y-4">
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Total Symbols</p>
                    <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>{totalSymbols}</p>
                  </div>
                  <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Fresh (Hourly)</p>
                    <p className="text-xl font-mono text-green-400">{db.recent_1h_symbols.length - staleHourly.length}</p>
                  </div>
                  <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Stale (&gt;2h)</p>
                    <p className={`text-xl font-mono ${staleHourly.length > 0 ? 'text-amber-400' : 'text-green-400'}`}>{staleHourly.length}</p>
                  </div>
                  <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Coverage</p>
                    <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>
                      {totalSymbols > 0 ? `${(((totalSymbols - staleHourly.length) / totalSymbols) * 100).toFixed(0)}%` : '—'}
                    </p>
                  </div>
                </div>
                {staleHourly.length > 0 && (
                  <div>
                    <p className="text-xs font-medium mb-2" style={{ color: 'var(--color-text-secondary)' }}>Stale Symbols (hourly data &gt;2h old):</p>
                    <div className="flex flex-wrap gap-1.5">
                      {staleHourly.slice(0, 20).map(s => (
                        <span key={s.symbol} className="px-2 py-0.5 rounded text-xs font-mono bg-amber-500/10 text-amber-400 border border-amber-500/20">
                          {s.symbol}
                        </span>
                      ))}
                      {staleHourly.length > 20 && (
                        <span className="px-2 py-0.5 rounded text-xs font-mono text-amber-400">+{staleHourly.length - 20} more</span>
                      )}
                    </div>
                  </div>
                )}
                <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                  Note: Per-symbol sync is not available — only full sync is supported. Use "Run Sync Now" above to refresh all symbols.
                </p>
              </div>
            );
          })() : (
            <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>No symbol data available yet.</p>
          )}
        </div>

        {/* Monitoring Processes Status */}
        {monitoringStatus && (
          <div className="space-y-4">
            {/* Main Loop Tasks */}
            <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
              <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>
                Main Loop (30-60s cycle)
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.values(monitoringStatus.main_loop || {}).map((task: any) => (
                  <div key={task.name} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-2 h-2 rounded-full ${
                        task.status === 'healthy' ? 'bg-green-400' :
                        task.age === 'never' ? 'bg-gray-500' : 'bg-amber-400'
                      }`} />
                      <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>{task.name}</p>
                    </div>
                    <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>{task.age}</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>every {task.interval}</p>
                    {task.pending_count > 0 && (
                      <p className="text-xs mt-1 text-amber-400">{task.pending_count} pending</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Background Threads */}
            <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
              <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>
                Background Threads
              </h3>
              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                {Object.values(monitoringStatus.background || {}).map((task: any) => (
                  <div key={task.name} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="flex items-center gap-2 mb-2">
                      <div className={`w-2 h-2 rounded-full ${
                        task.status === 'healthy' ? 'bg-green-400' :
                        task.age === 'never' ? 'bg-gray-500' :
                        task.status === 'stale' ? 'bg-amber-400' : 'bg-green-400'
                      }`} />
                      <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>{task.name}</p>
                    </div>
                    <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>{task.age}</p>
                    <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>every {task.interval}</p>
                    {task.symbols_updated > 0 && (
                      <p className="text-xs mt-1 text-green-400">{task.symbols_updated} symbols • {task.duration_s}s</p>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Daily Tasks */}
            <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
              <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>
                Daily Tasks
              </h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                {Object.values(monitoringStatus.daily || {}).map((task: any) => (
                  <div key={task.name} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs font-mono mb-2" style={{ color: 'var(--color-text-secondary)' }}>{task.name}</p>
                    <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>{task.age}</p>
                  </div>
                ))}
              </div>
            </div>

            {/* System Status */}
            {monitoringStatus.system && (
              <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
                <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>System & APIs</h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
                  {monitoringStatus.system.strategies && (
                    <>
                      <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                        <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Active (DEMO/LIVE)</p>
                        <p className="text-xl font-mono text-green-400">{monitoringStatus.system.strategies.active_demo_live}</p>
                      </div>
                      <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                        <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Backtested (Scanning)</p>
                        <p className="text-xl font-mono text-blue-400">{monitoringStatus.system.strategies.backtested_scanning}</p>
                      </div>
                      <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                        <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>Open Positions</p>
                        <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>{monitoringStatus.system.strategies.open_positions}</p>
                      </div>
                    </>
                  )}
                  {monitoringStatus.system.fmp && (
                    <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-2 h-2 rounded-full ${
                          monitoringStatus.system.fmp.status === 'healthy' ? 'bg-green-400' :
                          monitoringStatus.system.fmp.status === 'circuit_breaker' ? 'bg-red-400' :
                          'bg-gray-500'
                        }`} />
                        <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>FMP API</p>
                      </div>
                      <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                        {monitoringStatus.system.fmp.calls_today ?? '?'}/{monitoringStatus.system.fmp.max_calls ?? '?'} calls
                      </p>
                      <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                        {monitoringStatus.system.fmp.usage_percent ?? 0}% used • {monitoringStatus.system.fmp.cache_size ?? 0} cached
                      </p>
                    </div>
                  )}
                  {monitoringStatus.system.fred && (
                    <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <div className="flex items-center gap-2 mb-2">
                        <div className={`w-2 h-2 rounded-full ${
                          monitoringStatus.system.fred.status === 'healthy' ? 'bg-green-400' :
                          monitoringStatus.system.fred.status === 'disabled' ? 'bg-gray-500' :
                          'bg-amber-400'
                        }`} />
                        <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>FRED API</p>
                      </div>
                      <p className="text-sm font-mono" style={{ color: 'var(--color-text-primary)' }}>
                        {monitoringStatus.system.fred.enabled ? 'Enabled' : 'Disabled'}
                      </p>
                      {monitoringStatus.system.fred.last_fetch_age && (
                        <p className="text-xs mt-1" style={{ color: 'var(--color-text-secondary)' }}>
                          Last fetch: {monitoringStatus.system.fred.last_fetch_age}
                        </p>
                      )}
                    </div>
                  )}
                  {monitoringStatus.system.circuit_breakers && (
                    <div className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <p className="text-xs font-mono mb-2" style={{ color: 'var(--color-text-secondary)' }}>eToro Circuit Breakers</p>
                      {Object.entries(monitoringStatus.system.circuit_breakers).map(([name, state]: [string, any]) => (
                        <div key={name} className="flex items-center gap-2 text-xs">
                          <div className={`w-1.5 h-1.5 rounded-full ${
                            state.state === 'closed' ? 'bg-green-400' :
                            state.state === 'open' ? 'bg-red-400' : 'bg-amber-400'
                          }`} />
                          <span style={{ color: 'var(--color-text-primary)' }}>{name}: {state.state}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Live Sync Log */}
        {logs.length > 0 && (
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-3" style={{ color: 'var(--color-text-primary)' }}>
              Sync Log {isRunning && <span className="text-amber-400 text-sm animate-pulse ml-2">● live</span>}
            </h3>
            <div
              className="rounded-lg p-4 font-mono text-xs overflow-y-auto"
              style={{ backgroundColor: '#0d1117', maxHeight: '300px', color: '#8b949e' }}
            >
              {logs.map((line, i) => (
                <div key={i} className={`py-0.5 ${
                  line.includes('ERROR') || line.includes('FATAL') ? 'text-red-400' :
                  line.includes('DONE') ? 'text-green-400' :
                  line.includes('Progress') ? 'text-blue-400' :
                  ''
                }`}>
                  {line}
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}

        {/* DB Stats */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>Database Cache</h3>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { label: 'Total Bars', value: db?.total_bars?.toLocaleString() ?? '—' },
              { label: 'Symbols', value: db?.unique_symbols ?? '—' },
              { label: 'Daily (1d)', value: db?.by_interval?.['1d']?.toLocaleString() ?? '0' },
              { label: 'Hourly (1h)', value: db?.by_interval?.['1h']?.toLocaleString() ?? '0' },
              { label: 'Latest Bar', value: db?.latest_bar ? formatAge(db.latest_bar) : '—' },
            ].map(({ label, value }) => (
              <div key={label} className="rounded-lg p-4" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                <p className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                <p className="text-xl font-mono" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Recent 1h Data */}
        {db?.recent_1h_symbols && db.recent_1h_symbols.length > 0 && (
          <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
            <h3 className="text-lg font-mono mb-4" style={{ color: 'var(--color-text-primary)' }}>
              Recent Hourly Data (Top 5)
            </h3>
            <table className="w-full text-sm font-mono">
              <thead>
                <tr style={{ color: 'var(--color-text-secondary)' }}>
                  <th className="text-left py-2 px-3">Symbol</th>
                  <th className="text-left py-2 px-3">Latest 1h Bar</th>
                  <th className="text-left py-2 px-3">Age</th>
                </tr>
              </thead>
              <tbody>
                {db.recent_1h_symbols.map((item) => {
                  const age = (Date.now() - new Date(item.latest).getTime()) / 1000;
                  return (
                    <tr key={item.symbol} style={{ borderTop: '1px solid var(--color-dark-border)' }}>
                      <td className="py-2 px-3" style={{ color: 'var(--color-text-primary)' }}>{item.symbol}</td>
                      <td className="py-2 px-3" style={{ color: 'var(--color-text-secondary)' }}>
                        {new Date(item.latest).toLocaleString()}
                      </td>
                      <td className="py-2 px-3">
                        <span className={age < 7200 ? 'text-green-400' : 'text-amber-400'}>
                          {formatAge(item.latest)}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Architecture Info */}
        <div className="rounded-lg border p-6" style={{ backgroundColor: 'var(--color-dark-surface)', borderColor: 'var(--color-dark-border)' }}>
          <h3 className="text-lg font-mono mb-3" style={{ color: 'var(--color-text-primary)' }}>Data Architecture</h3>
          <div className="space-y-2 text-sm" style={{ color: 'var(--color-text-secondary)' }}>
            <p>◆ Hourly sync fetches 1d + 1h bars for all 117 symbols → persisted to DB</p>
            <p>◆ Crypto + forex sync 24/7. Stocks/ETFs sync 1h during market hours only.</p>
            <p>◆ Active strategy symbols also loaded into in-memory cache for instant signal generation.</p>
            <p>◆ Signal generation runs immediately after each sync completes.</p>
            <p>◆ Manual autonomous cycles read from DB — no Yahoo Finance calls needed.</p>
          </div>
        </div>
        </>
        )}
      </div>
    </DashboardLayout>
  );
};
