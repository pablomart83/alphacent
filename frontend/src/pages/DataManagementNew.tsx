import { type FC, useState, useCallback, useRef, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { CompactMetricRow, type CompactMetric } from '../components/trading/CompactMetricRow';
import { RefreshCw } from 'lucide-react';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';
import { cn } from '../lib/utils';
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
  const [fmpCacheWarming, setFmpCacheWarming] = useState(false);
  const [fmpCacheStatus, setFmpCacheStatus] = useState<any>(null);
  const [newsSentimentStatus, setNewsSentimentStatus] = useState<any>(null);
  const [newsSentimentSyncing, setNewsSentimentSyncing] = useState(false);
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
      const [data, monData, dqData, fmpData, sentData] = await Promise.all([
        apiClient.getDataSyncStatus() as Promise<SyncStatus>,
        apiClient.getMonitoringStatus().catch(() => null),
        apiClient.getDataQuality().catch(() => []),
        apiClient.getFmpCacheStatus().catch(() => null),
        apiClient.get('/data/news-sentiment/status').catch(() => null),
      ]);
      setStatus(data);
      if (monData) setMonitoringStatus(monData);
      if (dqData) setDataQuality(dqData);
      if (fmpData) {
        setFmpCacheStatus(fmpData);
        setFmpCacheWarming(fmpData.running);
      }
      if (sentData) {
        setNewsSentimentStatus(sentData);
        setNewsSentimentSyncing(sentData.running);
      }
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

  const handleTriggerFmpCacheWarm = async () => {
    setFmpCacheWarming(true);
    try {
      const result = await apiClient.triggerFmpCacheWarm();
      if (result.success) {
        toast.success('FMP cache warm started — polling for progress...');
        // Give the thread 5s to start before polling
        // Then poll every 3s, but require running=false for 2 consecutive polls
        // before declaring it done (handles thread startup race)
        let notRunningCount = 0;
        const poll = setInterval(async () => {
          try {
            const s = await apiClient.getFmpCacheStatus();
            setFmpCacheStatus(s);
            if (!s.running) {
              notRunningCount++;
              if (notRunningCount >= 2) {
                clearInterval(poll);
                setFmpCacheWarming(false);
                if (s.error) {
                  toast.error(`FMP cache warm failed: ${s.error}`);
                } else if (s.completed_at) {
                  toast.success(`FMP cache warm complete — ${s.fetched} fetched, ${s.cached} cached (${s.coverage_pct}% coverage)`);
                }
              }
            } else {
              notRunningCount = 0; // reset if it starts running
            }
          } catch { /* ignore poll errors */ }
        }, 3000);
        // Safety: stop polling after 20 minutes regardless
        setTimeout(() => { clearInterval(poll); setFmpCacheWarming(false); }, 20 * 60 * 1000);
      } else {
        toast.error(result.message);
        setFmpCacheWarming(false);
      }
    } catch {
      toast.error('Failed to trigger FMP cache warm');
      setFmpCacheWarming(false);
    }
  };

  const handleTriggerNewsSentimentSync = async () => {
    setNewsSentimentSyncing(true);
    try {
      const result = await apiClient.post('/data/news-sentiment/trigger');
      if (result.success) {
        toast.success('News sentiment sync started...');
        let notRunningCount = 0;
        const poll = setInterval(async () => {
          try {
            const s = await apiClient.get('/data/news-sentiment/status');
            setNewsSentimentStatus(s);
            if (!s.running) {
              notRunningCount++;
              if (notRunningCount >= 2) {
                clearInterval(poll);
                setNewsSentimentSyncing(false);
                if (s.error) toast.error(`Sentiment sync failed: ${s.error}`);
                else if (s.completed_at) toast.success(`Sentiment sync complete — ${s.fetched} fetched (${s.coverage_pct?.toFixed(1)}% coverage)`);
              }
            } else { notRunningCount = 0; }
          } catch { /* ignore */ }
        }, 3000);
        setTimeout(() => { clearInterval(poll); setNewsSentimentSyncing(false); }, 10 * 60 * 1000);
      } else {
        toast.error(result.message);
        setNewsSentimentSyncing(false);
      }
    } catch {
      toast.error('Failed to trigger sentiment sync');
      setNewsSentimentSyncing(false);
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

  // ── Compute side panel metrics ──────────────────────────────────────
  const healthyCnt = useMemo(() => dataQuality.filter((d: any) => d.quality_score > 80).length, [dataQuality]);
  const degradedCnt = useMemo(() => dataQuality.filter((d: any) => d.quality_score >= 60 && d.quality_score <= 80).length, [dataQuality]);
  const staleCnt = useMemo(() => dataQuality.filter((d: any) => d.quality_score < 60).length, [dataQuality]);
  const avgScore = useMemo(() => {
    if (dataQuality.length === 0) return 0;
    return Math.round(dataQuality.reduce((sum: number, d: any) => sum + (d.quality_score ?? 0), 0) / dataQuality.length);
  }, [dataQuality]);

  const sideMetrics: CompactMetric[] = useMemo(() => [
    { label: 'Healthy', value: healthyCnt, trend: 'up' as const, color: '#22c55e' },
    { label: 'Degraded', value: degradedCnt, trend: degradedCnt > 0 ? 'down' as const : 'neutral' as const, color: '#eab308' },
    { label: 'Stale', value: staleCnt, trend: staleCnt > 0 ? 'down' as const : 'neutral' as const, color: '#ef4444' },
    { label: 'Avg Score', value: avgScore, trend: avgScore > 80 ? 'up' as const : avgScore >= 60 ? 'neutral' as const : 'down' as const },
  ], [healthyCnt, degradedCnt, staleCnt, avgScore]);

  // ── Header actions ──────────────────────────────────────────────────
  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <button onClick={fetchStatus} disabled={loading} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Refresh">
        <RefreshCw className={cn('h-3.5 w-3.5', loading && 'animate-spin')} />
      </button>
    </div>
  );

  // ── Main Panel (65%) — Data Quality DenseTable ──────────────────────
  const mainPanel = (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Data Quality"
        panelId="data-main"
        onRefresh={fetchStatus}
        actions={
          <div className="flex items-center gap-1">
            <select
              value={dqFilterClass}
              onChange={(e) => setDqFilterClass(e.target.value)}
              className="text-xs font-mono rounded px-1.5 py-0.5 border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            >
              <option value="all">All Classes</option>
              {assetClasses.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
            <select
              value={dqFilterScore}
              onChange={(e) => setDqFilterScore(e.target.value)}
              className="text-xs font-mono rounded px-1.5 py-0.5 border"
              style={{ backgroundColor: 'var(--color-dark-bg)', borderColor: 'var(--color-dark-border)', color: 'var(--color-text-primary)' }}
            >
              <option value="all">All Scores</option>
              <option value="green">Good (&gt;80)</option>
              <option value="yellow">Warning (60-80)</option>
              <option value="red">Critical (&lt;60)</option>
            </select>
          </div>
        }
      >
        <div className="flex-1 overflow-auto min-h-0 h-full">
          {/* Stale Data Warning Banner */}
          {(() => {
            if (!db?.recent_1h_symbols || db.recent_1h_symbols.length === 0) return null;
            const staleSymbols = db.recent_1h_symbols.filter(s => {
              const ageMs = Date.now() - new Date(s.latest).getTime();
              return ageMs > 2 * 60 * 60 * 1000;
            });
            const totalSymbols = db.unique_symbols || db.recent_1h_symbols.length;
            const stalePercent = totalSymbols > 0 ? (staleSymbols.length / totalSymbols) * 100 : 0;
            if (stalePercent <= 10) return null;
            return (
              <div className="mx-3 mt-2 rounded-lg border p-2" style={{ backgroundColor: 'rgba(245, 158, 11, 0.1)', borderColor: 'rgba(245, 158, 11, 0.3)' }}>
                <div className="flex items-center gap-2">
                  <span className="text-amber-400 text-sm">⚠</span>
                  <p className="text-xs text-amber-400">
                    {staleSymbols.length} of {totalSymbols} symbols ({stalePercent.toFixed(0)}%) stale (&gt;2h). Consider syncing.
                  </p>
                </div>
              </div>
            );
          })()}

          {/* DenseTable — data quality for 297 symbols */}
          {filteredDq.length > 0 ? (
            <div className="overflow-auto h-full">
              <table className="w-full text-xs font-mono">
                <thead className="sticky top-0 z-10" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <tr style={{ color: 'var(--color-text-secondary)' }}>
                    {[
                      { key: 'symbol', label: 'Symbol' },
                      { key: 'asset_class', label: 'Class' },
                      { key: 'quality_score', label: 'Price' },
                      { key: 'fmp_score', label: 'Fundamentals' },
                      { key: 'sentiment_score', label: 'News' },
                      { key: 'last_price_update', label: 'Updated' },
                      { key: 'data_source', label: 'Source' },
                      { key: 'active_issues', label: 'Issues' },
                    ].map((col) => (
                      <th
                        key={col.key}
                        className="text-left py-1.5 px-2 cursor-pointer hover:text-gray-300 text-xs font-semibold uppercase tracking-wide"
                        onClick={() => handleDqSort(col.key)}
                      >
                        {col.label} {dqSortKey === col.key ? (dqSortAsc ? '↑' : '↓') : ''}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filteredDq.map((row: any) => (
                    <tr
                      key={row.symbol}
                      className="hover:bg-[var(--color-dark-bg)] transition-colors"
                      style={{ borderTop: '1px solid var(--color-dark-border)' }}
                    >
                      <td className="py-1 px-2" style={{ color: 'var(--color-text-primary)' }}>
                        {row.symbol}
                        {row.quality_score < 60 && <span className="ml-1 text-red-400 text-xs" title="Low quality">⚠</span>}
                      </td>
                      <td className="py-1 px-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.asset_class || '—'}</td>
                      {/* Price quality score */}
                      <td className="py-1 px-2 font-semibold" style={{ color: row.quality_score != null ? scoreColor(row.quality_score) : 'var(--color-text-secondary)' }}>
                        {row.quality_score != null ? row.quality_score : <span className="text-gray-500">—</span>}
                      </td>
                      {/* FMP Fundamentals */}
                      <td className="py-1 px-2">
                        {row.fmp_score == null ? (
                          <span className="text-xs text-gray-600">n/a</span>
                        ) : row.fmp_has_data ? (
                          <span className="text-xs font-mono" style={{ color: scoreColor(row.fmp_score) }}>
                            {row.fmp_score.toFixed(0)}
                            {row.fmp_age_days != null && <span className="text-gray-500 ml-1">{row.fmp_age_days < 1 ? '<1d' : `${row.fmp_age_days.toFixed(0)}d`}</span>}
                          </span>
                        ) : (
                          <span className="text-xs text-red-400">missing</span>
                        )}
                      </td>
                      {/* News sentiment */}
                      <td className="py-1 px-2">
                        {row.sentiment_score == null ? (
                          <span className="text-xs text-gray-600">—</span>
                        ) : (
                          <span className="text-xs font-mono" style={{
                            color: row.sentiment_label === 'bullish' ? '#22c55e' :
                                   row.sentiment_label === 'bearish' ? '#ef4444' : '#9ca3af'
                          }}>
                            {row.sentiment_score > 0 ? '+' : ''}{row.sentiment_score.toFixed(2)}
                            <span className="text-gray-600 ml-1">
                              {row.sentiment_age_hours != null ? (row.sentiment_age_hours < 1 ? '<1h' : `${row.sentiment_age_hours.toFixed(0)}h`) : ''}
                            </span>
                          </span>
                        )}
                      </td>
                      <td className="py-1 px-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.last_price_update ? formatAge(row.last_price_update) : '—'}</td>
                      <td className="py-1 px-2 text-xs" style={{ color: 'var(--color-text-secondary)' }}>{row.data_source || '—'}</td>
                      <td className="py-1 px-2" style={{ color: (row.active_issues ?? 0) > 0 ? '#eab308' : 'var(--color-text-secondary)' }}>{row.active_issues ?? 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="flex items-center justify-center h-full p-6">
              <p className="text-sm" style={{ color: 'var(--color-text-secondary)' }}>
                {dataQuality.length === 0 ? 'Data quality report not available yet.' : 'No symbols match the current filters.'}
              </p>
            </div>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Side Panel (35%) — Data Health ──────────────────────────────────
  const sidePanel = (
    <div className="flex flex-col h-full">
      <PanelHeader
        title="Data Health"
        panelId="data-side"
        onRefresh={fetchStatus}
      >
        <div className="flex flex-col gap-1 p-1.5 h-full">
          {/* CompactMetricRow: healthy/degraded/stale counts + avg score */}
          <CompactMetricRow metrics={sideMetrics} />

          {/* Data Source Health Cards */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">Data Source Health</div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { name: 'eToro', data: monitoringStatus?.system?.etoro },
                { name: 'Yahoo', data: monitoringStatus?.system?.yahoo },
                { name: 'FMP', data: monitoringStatus?.system?.fmp },
                { name: 'FRED', data: monitoringStatus?.system?.fred },
                { name: 'Marketaux', data: newsSentimentStatus ? {
                    status: (newsSentimentStatus.requests_remaining ?? 95) > 10 ? 'healthy' :
                            (newsSentimentStatus.requests_remaining ?? 95) > 0 ? 'degraded' : 'rate_limited',
                    coverage: `${(newsSentimentStatus.coverage_pct ?? 0).toFixed(0)}%`,
                    req_remaining: newsSentimentStatus.requests_remaining ?? '—',
                  } : null },
              ].map(({ name, data }) => (
                <div key={name} className="rounded-lg p-2" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div className="flex items-center gap-1.5 mb-1">
                    <div className={`w-2 h-2 rounded-full ${
                      data?.status === 'healthy' ? 'bg-green-400' :
                      data?.status === 'configured' ? 'bg-blue-400' :
                      data?.status === 'degraded' ? 'bg-amber-400' :
                      data?.status === 'disabled' || data?.status === 'no_api_key' || data?.status === 'rate_limited' ? 'bg-gray-500' :
                      !data ? 'bg-gray-600' : 'bg-red-400'
                    }`} />
                    <span className="text-xs font-mono font-semibold" style={{ color: 'var(--color-text-primary)' }}>{name}</span>
                  </div>
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    <span className={
                      data?.status === 'healthy' ? 'text-green-400' :
                      data?.status === 'configured' ? 'text-blue-400' :
                      data?.status === 'degraded' ? 'text-amber-400' :
                      'text-gray-500'
                    }>{data?.status ?? 'unknown'}</span>
                  </p>
                  {data?.coverage != null && (
                    <p className="text-xs font-mono mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                      {data.coverage} coverage
                    </p>
                  )}
                  {data?.req_remaining != null && (
                    <p className="text-xs font-mono" style={{ color: (data.req_remaining as number) < 20 ? '#ef4444' : 'var(--color-text-secondary)' }}>
                      {data.req_remaining} req left
                    </p>
                  )}
                  {data?.error_count != null && (
                    <p className="text-xs mt-0.5" style={{ color: data.error_count > 0 ? '#ef4444' : 'var(--color-text-secondary)' }}>
                      Err: {data.error_count}
                    </p>
                  )}
                  {data?.avg_response_ms != null && (
                    <p className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>{data.avg_response_ms}ms</p>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* FMP Cache Status */}
          {monitoringStatus?.system?.fmp && (
            <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
              <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">FMP Cache</div>
              <div className="space-y-2">
                {/* Rate limit — per-minute sliding window */}
                <div className="flex items-center justify-between">
                  <span className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Rate (per min)</span>
                  <span className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>
                    {monitoringStatus.system.fmp.calls_today ?? 0}/{monitoringStatus.system.fmp.max_calls ?? 300}
                  </span>
                </div>
                <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-500"
                    style={{
                      width: `${Math.min(100, monitoringStatus.system.fmp.usage_percent ?? 0)}%`,
                      backgroundColor: (monitoringStatus.system.fmp.usage_percent ?? 0) > 80 ? '#ef4444' : (monitoringStatus.system.fmp.usage_percent ?? 0) > 50 ? '#f59e0b' : '#22c55e',
                    }}
                  />
                </div>
                {/* DB cache coverage — the real picture */}
                <div className="grid grid-cols-3 gap-1.5">
                  <div className="rounded p-1.5" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>DB Total</p>
                    <p className="text-xs font-mono text-blue-400">{monitoringStatus.system.fmp.cache_size ?? 0}</p>
                  </div>
                  <div className="rounded p-1.5" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Fresh 7d</p>
                    <p className="text-xs font-mono text-green-400">{monitoringStatus.system.fmp.cache_fresh_7d ?? 0}</p>
                  </div>
                  <div className="rounded p-1.5" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>Fresh 24h</p>
                    <p className="text-xs font-mono text-green-400">{monitoringStatus.system.fmp.cache_fresh_24h ?? 0}</p>
                  </div>
                </div>
                {monitoringStatus.system.fmp.last_warm_time && (
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>
                    Last warm: {formatAge(monitoringStatus.system.fmp.last_warm_time)}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* Sync Progress */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">Sync Progress</div>
            <div className="space-y-3">
              {/* Quick Update (10min) */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>Quick Update</span>
                  <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                    {status?.quick_update?.timestamp ? formatAge(status.quick_update.timestamp) : '—'}
                  </span>
                </div>
                <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{
                      width: quickUpdating ? '60%' : '100%',
                      backgroundColor: quickUpdating ? '#eab308' : '#22c55e',
                      animation: quickUpdating ? 'pulse 1.5s ease-in-out infinite' : 'none',
                    }}
                  />
                </div>
                <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  <span>{status?.quick_update?.updated ?? 0} symbols</span>
                  <span>10min cycle</span>
                </div>
              </div>
              {/* Full Sync */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>Full Sync</span>
                  <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                    {status?.last_sync_at ? formatAge(status.last_sync_at) : '—'}
                  </span>
                </div>
                <div className="w-full h-1.5 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <div
                    className="h-full rounded-full transition-all duration-1000"
                    style={{
                      width: isRunning ? `${Math.min(95, ((status?.sync_elapsed_s ?? 0) / (status?.last_sync_duration_s ?? 60)) * 100)}%` : '100%',
                      backgroundColor: isRunning ? '#3b82f6' : '#22c55e',
                      animation: isRunning ? 'pulse 1.5s ease-in-out infinite' : 'none',
                    }}
                  />
                </div>
                <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                  <span>{db?.unique_symbols ?? 0} symbols</span>
                  <span>{status ? `${Math.round(status.sync_interval_s / 60)}min` : '—'}</span>
                </div>
              </div>
            </div>
            {/* Sync action buttons */}
            <div className="flex gap-2 mt-3">
              <button
                onClick={handleTriggerSync}
                disabled={isRunning}
                className="flex-1 px-2 py-1.5 rounded text-xs font-mono transition-all duration-200 disabled:opacity-50"
                style={{
                  backgroundColor: isRunning ? 'var(--color-dark-bg)' : 'var(--color-accent-green)',
                  color: isRunning ? 'var(--color-text-secondary)' : '#000',
                }}
              >
                {isRunning ? `⟳ Syncing${status?.sync_elapsed_s ? ` (${status.sync_elapsed_s}s)` : ''}` : '▶ Full Sync'}
              </button>
              <button
                onClick={handleTriggerQuickUpdate}
                disabled={quickUpdating}
                className="flex-1 px-2 py-1.5 rounded text-xs font-mono transition-all duration-200 disabled:opacity-50"
                style={{
                  backgroundColor: quickUpdating ? 'var(--color-dark-bg)' : 'var(--color-accent-green)',
                  color: quickUpdating ? 'var(--color-text-secondary)' : '#000',
                }}
              >
                {quickUpdating ? '⟳ Updating...' : '▶ Quick'}
              </button>
            </div>
          </div>

          {/* FMP Fundamental Cache */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-gray-500 tracking-wide font-medium">Fundamental Cache (FMP)</div>
              {fmpCacheStatus?.last_warm_at && (
                <span className="text-xs font-mono" style={{ color: 'var(--color-text-secondary)' }}>
                  {formatAge(fmpCacheStatus.last_warm_at)}
                </span>
              )}
            </div>

            {/* Coverage bar */}
            {(() => {
              const pct = fmpCacheWarming
                ? fmpCacheStatus?.total > 0
                  ? Math.round((fmpCacheStatus.current / fmpCacheStatus.total) * 100)
                  : 0
                : (fmpCacheStatus?.coverage_pct ?? 0);
              const color = pct >= 80 ? '#22c55e' : pct >= 50 ? '#eab308' : '#ef4444';
              const label = fmpCacheWarming
                ? `${fmpCacheStatus?.current ?? 0} / ${fmpCacheStatus?.total ?? '?'} symbols`
                : `${fmpCacheStatus?.fresh_count ?? 0} / ${fmpCacheStatus?.total_symbols ?? '?'} fresh`;
              return (
                <div className="mb-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>
                      Coverage
                    </span>
                    <span className="text-xs font-mono font-semibold" style={{ color }}>
                      {pct.toFixed(1)}%
                    </span>
                  </div>
                  <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div
                      className="h-full rounded-full transition-all duration-500"
                      style={{
                        width: `${Math.min(100, pct)}%`,
                        backgroundColor: color,
                        animation: fmpCacheWarming ? 'pulse 1.5s ease-in-out infinite' : 'none',
                      }}
                    />
                  </div>
                  <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                    <span>{label}</span>
                    {fmpCacheWarming && fmpCacheStatus?.elapsed_s && (
                      <span>{fmpCacheStatus.elapsed_s}s elapsed</span>
                    )}
                  </div>
                </div>
              );
            })()}

            {/* Stats row */}
            {fmpCacheWarming && fmpCacheStatus && (
              <div className="grid grid-cols-3 gap-1 mb-2">
                {[
                  { label: 'Fetched', value: fmpCacheStatus.fetched ?? 0, color: '#22c55e' },
                  { label: 'Cached', value: fmpCacheStatus.cached ?? 0, color: '#3b82f6' },
                  { label: 'Failed', value: fmpCacheStatus.failed ?? 0, color: '#ef4444' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded p-1 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="text-xs font-mono font-semibold" style={{ color }}>{value}</div>
                    <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
                  </div>
                ))}
              </div>
            )}

            {fmpCacheStatus?.error && (
              <div className="text-xs text-red-400 mb-2 font-mono truncate" title={fmpCacheStatus.error}>
                ✗ {fmpCacheStatus.error}
              </div>
            )}

            <button
              onClick={handleTriggerFmpCacheWarm}
              disabled={fmpCacheWarming}
              className="w-full px-2 py-1.5 rounded text-xs font-mono transition-all duration-200 disabled:opacity-50"
              style={{
                backgroundColor: fmpCacheWarming ? 'var(--color-dark-bg)' : '#3b82f6',
                color: fmpCacheWarming ? 'var(--color-text-secondary)' : '#fff',
              }}
            >
              {fmpCacheWarming
                ? `⟳ Warming... ${fmpCacheStatus?.current ?? 0}/${fmpCacheStatus?.total ?? '?'}`
                : '▶ Refresh Fundamentals'}
            </button>
          </div>

          {/* News Sentiment Cache (Marketaux) */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs text-gray-500 tracking-wide font-medium">News Sentiment (Marketaux)</div>
              {newsSentimentStatus?.requests_remaining != null && (
                <span className="text-xs font-mono" style={{ color: newsSentimentStatus.requests_remaining < 20 ? '#ef4444' : 'var(--color-text-secondary)' }}>
                  {newsSentimentStatus.requests_remaining} req left
                </span>
              )}
            </div>

            {/* Coverage bar */}
            {(() => {
              const pct = newsSentimentSyncing
                ? newsSentimentStatus?.total > 0 ? Math.round((newsSentimentStatus.current / newsSentimentStatus.total) * 100) : 0
                : (newsSentimentStatus?.coverage_pct ?? 0);
              const color = pct >= 80 ? '#22c55e' : pct >= 40 ? '#eab308' : '#ef4444';
              const label = newsSentimentSyncing
                ? `${newsSentimentStatus?.current ?? 0} / ${newsSentimentStatus?.total ?? '?'} symbols`
                : `${newsSentimentStatus?.total_cached ?? 0} / ${newsSentimentStatus?.total_applicable ?? '?'} cached`;
              return (
                <div className="mb-2">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>Coverage</span>
                    <span className="text-xs font-mono font-semibold" style={{ color }}>{pct.toFixed(1)}%</span>
                  </div>
                  <div className="w-full h-2 rounded-full overflow-hidden" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="h-full rounded-full transition-all duration-500" style={{
                      width: `${Math.min(100, pct)}%`, backgroundColor: color,
                      animation: newsSentimentSyncing ? 'pulse 1.5s ease-in-out infinite' : 'none',
                    }} />
                  </div>
                  <div className="flex justify-between text-xs mt-0.5" style={{ color: 'var(--color-text-secondary)' }}>
                    <span>{label}</span>
                    {newsSentimentSyncing && newsSentimentStatus?.elapsed_s && <span>{newsSentimentStatus.elapsed_s}s</span>}
                  </div>
                </div>
              );
            })()}

            {/* Stats: fresh 24h / 7d */}
            {newsSentimentStatus && !newsSentimentSyncing && (
              <div className="grid grid-cols-2 gap-1 mb-2">
                {[
                  { label: 'Fresh 24h', value: newsSentimentStatus.fresh_24h ?? 0, color: '#22c55e' },
                  { label: 'Fresh 7d', value: newsSentimentStatus.fresh_7d ?? 0, color: '#3b82f6' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded p-1 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="text-xs font-mono font-semibold" style={{ color }}>{value}</div>
                    <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
                  </div>
                ))}
              </div>
            )}

            {/* Score distribution — bullish / neutral / bearish breakdown */}
            {newsSentimentStatus?.score_distribution && !newsSentimentSyncing && (
              <div className="mb-2">
                <div className="text-xs mb-1" style={{ color: 'var(--color-text-secondary)' }}>
                  Score distribution
                  {newsSentimentStatus.score_distribution.avg_score != null && (
                    <span className="ml-1 font-mono" style={{
                      color: newsSentimentStatus.score_distribution.avg_score > 0.05 ? '#22c55e'
                           : newsSentimentStatus.score_distribution.avg_score < -0.05 ? '#ef4444'
                           : 'var(--color-text-secondary)'
                    }}>
                      (avg {newsSentimentStatus.score_distribution.avg_score > 0 ? '+' : ''}{newsSentimentStatus.score_distribution.avg_score.toFixed(3)})
                    </span>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-1">
                  {[
                    { label: '▲ Bullish', value: newsSentimentStatus.score_distribution.bullish ?? 0, color: '#22c55e' },
                    { label: '— Neutral', value: newsSentimentStatus.score_distribution.neutral ?? 0, color: '#6b7280' },
                    { label: '▼ Bearish', value: newsSentimentStatus.score_distribution.bearish ?? 0, color: '#ef4444' },
                  ].map(({ label, value, color }) => (
                    <div key={label} className="rounded p-1 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                      <div className="text-xs font-mono font-semibold" style={{ color }}>{value}</div>
                      <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Progress during sync */}
            {newsSentimentSyncing && newsSentimentStatus && (
              <div className="grid grid-cols-2 gap-1 mb-2">
                {[
                  { label: 'Fetched', value: newsSentimentStatus.fetched ?? 0, color: '#22c55e' },
                  { label: 'Failed', value: newsSentimentStatus.failed ?? 0, color: '#ef4444' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded p-1 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <div className="text-xs font-mono font-semibold" style={{ color }}>{value}</div>
                    <div className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</div>
                  </div>
                ))}
              </div>
            )}

            {newsSentimentStatus?.error && (
              <div className="text-xs text-red-400 mb-2 font-mono truncate">{newsSentimentStatus.error}</div>
            )}

            <button
              onClick={handleTriggerNewsSentimentSync}
              disabled={newsSentimentSyncing || (newsSentimentStatus?.requests_remaining ?? 95) < 5}
              className="w-full px-2 py-1.5 rounded text-xs font-mono transition-all duration-200 disabled:opacity-50"
              style={{
                backgroundColor: newsSentimentSyncing ? 'var(--color-dark-bg)' : '#8b5cf6',
                color: newsSentimentSyncing ? 'var(--color-text-secondary)' : '#fff',
              }}
            >
              {newsSentimentSyncing
                ? `⟳ Syncing... ${newsSentimentStatus?.current ?? 0}/${newsSentimentStatus?.total ?? '?'}`
                : (newsSentimentStatus?.requests_remaining ?? 95) < 5
                  ? '⚠ Rate limit reached'
                  : '▶ Refresh Sentiment'}
            </button>
          </div>

          {/* DB Stats Summary */}
          <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
            <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">Database Cache</div>
            <div className="grid grid-cols-2 gap-2">
              {[
                { label: 'Total Bars', value: db?.total_bars?.toLocaleString() ?? '—' },
                { label: 'Symbols', value: db?.unique_symbols ?? '—' },
                { label: 'Daily (1d)', value: db?.by_interval?.['1d']?.toLocaleString() ?? '0' },
                { label: 'Hourly (1h)', value: db?.by_interval?.['1h']?.toLocaleString() ?? '0' },
              ].map(({ label, value }) => (
                <div key={label} className="rounded p-1.5" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                  <p className="text-xs" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                  <p className="text-xs font-mono" style={{ color: 'var(--color-text-primary)' }}>{value}</p>
                </div>
              ))}
            </div>
          </div>

          {/* Sync Log (compact) */}
          {logs.length > 0 && (
            <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
              <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">
                Sync Log {isRunning && <span className="text-amber-400 animate-pulse ml-1">● live</span>}
              </div>
              <div
                className="rounded p-2 font-mono text-xs overflow-y-auto"
                style={{ backgroundColor: '#0d1117', maxHeight: '120px', color: '#8b949e' }}
              >
                {logs.slice(-20).map((line, i) => (
                  <div key={i} className={`py-0.5 ${
                    line.includes('ERROR') || line.includes('FATAL') ? 'text-red-400' :
                    line.includes('DONE') ? 'text-green-400' :
                    line.includes('Progress') ? 'text-blue-400' : ''
                  }`}>
                    {line}
                  </div>
                ))}
                <div ref={logEndRef} />
              </div>
            </div>
          )}

          {/* Last sync stats */}
          {stats && typeof stats === 'object' && 'daily_fetched' in stats && (
            <div className="border border-[var(--color-dark-border)] rounded-lg p-3">
              <div className="text-xs text-gray-500 tracking-wide font-medium mb-2">Last Sync Stats</div>
              <div className="grid grid-cols-3 gap-1.5">
                {[
                  { label: '1d Fetch', value: stats.daily_fetched, color: 'text-green-400' },
                  { label: '1d DB', value: stats.daily_cached, color: 'text-blue-400' },
                  { label: '1h Fetch', value: stats.hourly_fetched, color: 'text-green-400' },
                  { label: '1h DB', value: stats.hourly_cached, color: 'text-blue-400' },
                  { label: 'Memory', value: stats.memory_loaded, color: 'text-cyan-400' },
                  { label: 'Skipped', value: stats.weekend_skipped, color: 'text-gray-500' },
                ].map(({ label, value, color }) => (
                  <div key={label} className="rounded p-1.5 text-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
                    <p className={`text-xs font-mono ${color}`}>{value ?? 0}</p>
                    <p className="text-[8px]" style={{ color: 'var(--color-text-secondary)' }}>{label}</p>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </PanelHeader>
    </div>
  );

  // ── Render ──────────────────────────────────────────────────────────
  if (loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="📊 Data Management" description="Market data sync, DB cache, and data freshness" actions={headerActions} compact={true}>
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="📊 Data Management"
        description="Market data sync, DB cache, and data freshness"
        actions={headerActions}
        compact={true}
      >
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ duration: 0.3 }}
          className="h-full"
        >
          <RefreshIndicator visible={pollingRefreshing && !loading} />
          <ResizablePanelLayout
            layoutId="data-management-panels"
            direction="horizontal"
            panels={[
              {
                id: 'data-main',
                defaultSize: 65,
                minSize: 400,
                content: mainPanel,
              },
              {
                id: 'data-side',
                defaultSize: 35,
                minSize: 280,
                content: sidePanel,
              },
            ]}
          />
        </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
