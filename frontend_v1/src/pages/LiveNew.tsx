import { type FC, useState, useCallback, useEffect } from 'react';
import { RefreshCw, TrendingUp, TrendingDown, DollarSign, Activity, Shield } from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { ResizablePanelLayout } from '../components/layout/ResizablePanelLayout';
import { PanelHeader } from '../components/layout/PanelHeader';
import { Tabs, TabsContent } from '../components/ui/tabs';
import { Button } from '../components/ui/Button';
import { Switch } from '../components/ui/switch';
import { apiClient } from '../services/api';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { toast } from 'sonner';

interface LiveNewProps {
  onLogout: () => void;
}

export const LiveNew: FC<LiveNewProps> = ({ onLogout }) => {
  const [liveTab, setLiveTab] = useState('overview');
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Data state
  const [summary, setSummary] = useState<any>(null);
  const [positions, setPositions] = useState<any[]>([]);
  const [orders, setOrders] = useState<any[]>([]);
  const [divergence, setDivergence] = useState<any[]>([]);
  const [graduationQueue, setGraduationQueue] = useState<any[]>([]);
  const [liveStrategies, setLiveStrategies] = useState<any[]>([]);
  const [liveConfig, setLiveConfig] = useState<any>(null);

  // Graduation form state
  const [selectedCandidate, setSelectedCandidate] = useState<any | null>(null);
  const [gradForm, setGradForm] = useState({ position_size: 500, sl_pct: 6, tp_pct: 15, conviction_min: 74, notes: '' });
  const [gradSubmitting, setGradSubmitting] = useState(false);

  const fetchAll = useCallback(async () => {
    setRefreshing(true);
    try {
      const [sumRes, posRes, ordRes, cfgRes] = await Promise.all([
        apiClient.getLiveSummary().catch(() => null),
        apiClient.get('/account/positions?mode=LIVE').catch(() => null),
        apiClient.get('/orders?mode=LIVE').catch(() => null),
        apiClient.getLiveTradingConfig().catch(() => null),
      ]);
      if (sumRes) setSummary(sumRes);
      if (posRes) setPositions(posRes.positions ?? []);
      if (ordRes) setOrders(ordRes.orders ?? []);
      if (cfgRes) setLiveConfig(cfgRes);
      setLoading(false);
    } catch (e) {
      console.error(e);
    } finally {
      setRefreshing(false);
    }
  }, []);

  const fetchGraduation = useCallback(async () => {
    const [qRes, lRes] = await Promise.all([
      apiClient.getGraduationQueue().catch(() => null),
      apiClient.getLiveStrategies().catch(() => null),
    ]);
    if (qRes) setGraduationQueue(qRes.queue ?? []);
    if (lRes) setLiveStrategies(lRes.live_strategies ?? []);
  }, []);

  const fetchDivergence = useCallback(async () => {
    const res = await apiClient.getLiveDivergence().catch(() => null);
    if (res) setDivergence(res.divergence ?? []);
  }, []);

  useEffect(() => {
    fetchAll();
    fetchGraduation();
    fetchDivergence();
  }, [fetchAll, fetchGraduation, fetchDivergence]);

  const handleToggleLive = async (enabled: boolean) => {
    try {
      await apiClient.updateLiveTradingConfig({ enabled });
      setLiveConfig((c: any) => c ? { ...c, enabled } : c);
      setSummary((s: any) => s ? { ...s, live_enabled: enabled } : s);
      toast.success(enabled ? '● Live trading ENABLED' : '○ Live trading disabled');
    } catch (err: any) {
      toast.error(`Failed: ${err.message}`);
    }
  };

  const handleApprove = async () => {
    if (!selectedCandidate) return;
    if (!window.confirm(`Approve ${selectedCandidate.template_name} / ${selectedCandidate.symbol} for LIVE?\nVirtual: $${gradForm.position_size} → Real: $${(gradForm.position_size * 0.10).toFixed(0)}`)) return;
    setGradSubmitting(true);
    try {
      await apiClient.graduateStrategy(selectedCandidate.strategy_id, {
        symbol: selectedCandidate.symbol,
        position_size: gradForm.position_size,
        sl_pct: gradForm.sl_pct / 100,
        tp_pct: gradForm.tp_pct / 100,
        conviction_min: gradForm.conviction_min,
        notes: gradForm.notes || undefined,
      });
      toast.success(`✅ ${selectedCandidate.symbol} approved for live trading`);
      setSelectedCandidate(null);
      fetchGraduation();
    } catch (err: any) {
      toast.error(`Failed: ${err.message}`);
    } finally {
      setGradSubmitting(false);
    }
  };

  const handleReject = async (c: any) => {
    if (!window.confirm(`Reject ${c.template_name} / ${c.symbol}? 14-day cooldown.`)) return;
    try {
      await apiClient.rejectGraduation(c.strategy_id, { symbol: c.symbol });
      toast.success('Rejected — 14-day cooldown applied');
      fetchGraduation();
    } catch (err: any) {
      toast.error(`Failed: ${err.message}`);
    }
  };

  const liveEnabled = summary?.live_enabled ?? liveConfig?.enabled ?? false;
  const mirror = summary?.mirror_ratio ?? 0.10;

  const tabButtons = [
    { value: 'overview', label: 'Overview' },
    { value: 'positions', label: `Positions (${positions.length})` },
    { value: 'orders', label: `Orders (${orders.length})` },
    { value: 'graduation', label: `🎓 Graduation (${graduationQueue.length})` },
    { value: 'divergence', label: `Divergence (${divergence.length})` },
  ];


  const mainPanel = (
    <div className="flex flex-col h-full">
      <div className="flex items-center px-3 min-h-[32px] max-h-[32px] shrink-0 bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]">
        <div className="flex items-center gap-0.5 overflow-x-auto scrollbar-hide flex-1 min-w-0">
          {tabButtons.map(tab => (
            <button key={tab.value} onClick={() => setLiveTab(tab.value)}
              className={cn('px-3 py-1 text-[13px] font-medium rounded whitespace-nowrap transition-colors shrink-0',
                liveTab === tab.value ? 'bg-gray-700/60 text-gray-100' : 'text-gray-500 hover:text-gray-300 hover:bg-gray-800/40')}>
              {tab.label}
            </button>
          ))}
        </div>
        <button onClick={fetchAll} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors ml-2">
          <RefreshCw size={12} className={cn(refreshing && 'animate-spin')} />
        </button>
      </div>

      <div className="flex-1 min-h-0 overflow-auto">
        <Tabs value={liveTab} onValueChange={setLiveTab} className="flex flex-col h-full">
          <div className="flex-1 min-h-0 overflow-auto">

            {/* Overview Tab */}
            <TabsContent value="overview" className="p-3 space-y-4">
              {/* Master switch */}
              <div className={cn('rounded-lg border p-4 flex items-center justify-between',
                liveEnabled ? 'border-green-500/40 bg-green-500/5' : 'border-border/40 bg-muted/10')}>
                <div>
                  <div className="text-sm font-semibold text-gray-200">Live Trading Master Switch</div>
                  <div className="text-xs text-gray-500 mt-0.5">
                    {liveEnabled
                      ? '● ACTIVE — approved strategies are firing real fills'
                      : '○ DISABLED — all signals paper-trade on DEMO only'}
                  </div>
                </div>
                <Switch checked={liveEnabled} onCheckedChange={handleToggleLive} />
              </div>

              {/* Account metrics */}
              <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                {[
                  { label: 'Virtual Equity', value: formatCurrency(summary?.virtual_equity ?? 0), sub: `$${((summary?.virtual_equity ?? 0) * mirror).toFixed(0)} real` },
                  { label: "Today's P&L", value: formatCurrency(summary?.today_pnl_virtual ?? 0), sub: `$${((summary?.today_pnl_virtual ?? 0) * mirror).toFixed(2)} real`, color: (summary?.today_pnl_virtual ?? 0) >= 0 ? 'text-green-400' : 'text-red-400' },
                  { label: 'Open Positions', value: String(summary?.open_positions ?? 0), sub: `${summary?.deployed_pct ?? 0}% deployed` },
                  { label: 'Live Authorizations', value: String(summary?.active_live_authorizations ?? 0), sub: 'approved pairs' },
                ].map(m => (
                  <div key={m.label} className="rounded-lg border border-border/40 bg-muted/10 p-3">
                    <div className="text-xs text-gray-500">{m.label}</div>
                    <div className={cn('text-lg font-mono font-semibold mt-0.5', m.color ?? 'text-gray-100')}>{m.value}</div>
                    <div className="text-xs text-gray-500 mt-0.5">{m.sub}</div>
                  </div>
                ))}
              </div>

              {/* Mirror ratio info */}
              <div className="rounded border border-gray-700/40 bg-gray-800/20 p-3 text-xs text-gray-500">
                <span className="text-gray-400 font-medium">Mirror ratio: </span>
                {(mirror * 100).toFixed(0)}% — every $1,000 virtual order = ${(1000 * mirror).toFixed(0)} real exposure.
                {' '}Virtual balance: ${(summary?.virtual_balance ?? 10000).toLocaleString()} | Real investment: ${((summary?.virtual_balance ?? 10000) * mirror).toLocaleString()}
              </div>
            </TabsContent>

            {/* Positions Tab */}
            <TabsContent value="positions" className="p-2">
              {positions.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No live positions open</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                        <th className="py-1.5 px-2 text-left">Symbol</th>
                        <th className="py-1.5 px-2 text-left">Side</th>
                        <th className="py-1.5 px-2 text-right">Virtual</th>
                        <th className="py-1.5 px-2 text-right">Real</th>
                        <th className="py-1.5 px-2 text-right">Entry</th>
                        <th className="py-1.5 px-2 text-right">Current</th>
                        <th className="py-1.5 px-2 text-right">P&L (V)</th>
                        <th className="py-1.5 px-2 text-right">P&L (R)</th>
                        <th className="py-1.5 px-2 text-right">SL</th>
                        <th className="py-1.5 px-2 text-center">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {positions.map((p: any) => (
                        <tr key={p.id} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                          <td className="py-1.5 px-2 text-gray-200 font-semibold">{p.symbol}</td>
                          <td className={cn('py-1.5 px-2', p.side === 'BUY' || p.side === 'LONG' ? 'text-green-400' : 'text-red-400')}>{p.side}</td>
                          <td className="py-1.5 px-2 text-right text-gray-300">{p.invested_amount ? formatCurrency(p.invested_amount) : '—'}</td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{p.invested_amount ? formatCurrency(p.invested_amount * mirror) : '—'}</td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{p.entry_price?.toFixed(4)}</td>
                          <td className="py-1.5 px-2 text-right text-gray-300">{p.current_price?.toFixed(4)}</td>
                          <td className={cn('py-1.5 px-2 text-right', (p.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
                            {formatCurrency(p.unrealized_pnl ?? 0)}
                          </td>
                          <td className={cn('py-1.5 px-2 text-right', (p.unrealized_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
                            {formatCurrency((p.unrealized_pnl ?? 0) * mirror)}
                          </td>
                          <td className="py-1.5 px-2 text-right text-gray-500">{p.stop_loss?.toFixed(4) ?? '—'}</td>
                          <td className="py-1.5 px-2 text-center">
                            <button
                              onClick={async () => {
                                if (!window.confirm(`Close live ${p.symbol} position?`)) return;
                                try {
                                  await apiClient.closeLivePosition(p.id);
                                  toast.success(`Close order submitted for ${p.symbol}`);
                                  fetchAll();
                                } catch (err: any) { toast.error(err.message); }
                              }}
                              className="px-2 py-0.5 text-xs rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors"
                            >Close</button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>

            {/* Orders Tab */}
            <TabsContent value="orders" className="p-2">
              {orders.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No live orders</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                        <th className="py-1.5 px-2 text-left">Symbol</th>
                        <th className="py-1.5 px-2 text-left">Side</th>
                        <th className="py-1.5 px-2 text-right">Virtual</th>
                        <th className="py-1.5 px-2 text-right">Real</th>
                        <th className="py-1.5 px-2 text-left">Status</th>
                        <th className="py-1.5 px-2 text-right">Fill Price</th>
                        <th className="py-1.5 px-2 text-right">Slippage</th>
                        <th className="py-1.5 px-2 text-right">Fill Time</th>
                        <th className="py-1.5 px-2 text-right">Submitted</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((o: any) => (
                        <tr key={o.id} className="border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40">
                          <td className="py-1.5 px-2 text-gray-200 font-semibold">{o.symbol}</td>
                          <td className={cn('py-1.5 px-2', o.side === 'BUY' ? 'text-green-400' : 'text-red-400')}>{o.side}</td>
                          <td className="py-1.5 px-2 text-right text-gray-300">{formatCurrency(o.quantity)}</td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{formatCurrency(o.quantity * mirror)}</td>
                          <td className="py-1.5 px-2">
                            <span className={cn('px-1.5 py-0.5 rounded text-xs',
                              o.status === 'FILLED' ? 'bg-green-500/15 text-green-400' :
                              o.status === 'PENDING' ? 'bg-yellow-500/15 text-yellow-400' :
                              o.status === 'CANCELLED' ? 'bg-gray-700/40 text-gray-500' :
                              'bg-red-500/15 text-red-400'
                            )}>{o.status}</span>
                          </td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{o.filled_price?.toFixed(4) ?? '—'}</td>
                          <td className={cn('py-1.5 px-2 text-right', o.slippage != null && o.slippage > 0.001 ? 'text-yellow-400' : 'text-gray-500')}>
                            {o.slippage != null ? `${(o.slippage * 100).toFixed(3)}%` : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-right text-gray-500">
                            {o.fill_time_seconds != null ? `${o.fill_time_seconds.toFixed(1)}s` : '—'}
                          </td>
                          <td className="py-1.5 px-2 text-right text-gray-500">
                            {o.created_at ? new Date(o.created_at).toLocaleString('en-GB', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>


            {/* Graduation Tab */}
            <TabsContent value="graduation" className="p-3 space-y-3">
              <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-xs text-amber-300">
                <div className="font-semibold">⚠ HARD GATE</div>
                <div>Live fills only fire when the master switch above is ON. Approving here is necessary but not sufficient.</div>
              </div>

              <div className="text-xs font-medium text-gray-400 mb-1">Qualified Candidates ({graduationQueue.length})</div>
              {graduationQueue.length === 0 ? (
                <div className="text-xs text-gray-500 py-4 text-center">No strategies qualify yet. Criteria: ≥20 paper trades, Sharpe ≥60% of WF, win rate ≥45%, P&L &gt; 0.</div>
              ) : (
                <div className="space-y-2">
                  {graduationQueue.map((c: any) => (
                    <div key={`${c.strategy_id}-${c.symbol}`}
                      className={cn('rounded-lg border p-3 cursor-pointer transition-colors',
                        selectedCandidate?.strategy_id === c.strategy_id && selectedCandidate?.symbol === c.symbol
                          ? 'border-blue-500/60 bg-blue-500/10' : 'border-border/40 bg-muted/10 hover:border-border/70')}
                      onClick={() => { setSelectedCandidate(c); setGradForm({ position_size: 500, sl_pct: 6, tp_pct: 15, conviction_min: 74, notes: '' }); }}>
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <div className="text-xs font-semibold text-gray-200 truncate">{c.template_name}</div>
                          <div className="text-xs text-gray-400 mt-0.5">{c.symbol}</div>
                        </div>
                        <span className="text-xs font-mono text-green-400 font-semibold shrink-0">
                          {c.qualification_ratio != null ? `${(c.qualification_ratio * 100).toFixed(0)}%` : '—'} ratio
                        </span>
                      </div>
                      <div className="grid grid-cols-4 gap-2 mt-2 text-xs">
                        <div><span className="text-gray-500">Trades</span><div className="font-mono text-gray-200">{c.paper_trades}</div></div>
                        <div><span className="text-gray-500">Sharpe</span><div className="font-mono text-gray-200">{c.paper_sharpe?.toFixed(2) ?? '—'}</div></div>
                        <div><span className="text-gray-500">Win%</span><div className="font-mono text-gray-200">{c.paper_win_rate != null ? `${(c.paper_win_rate * 100).toFixed(0)}%` : '—'}</div></div>
                        <div><span className="text-gray-500">P&L</span><div className={cn('font-mono', (c.paper_total_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>{c.paper_total_pnl != null ? formatCurrency(c.paper_total_pnl) : '—'}</div></div>
                      </div>
                      <div className="flex gap-2 mt-2">
                        <button onClick={e => { e.stopPropagation(); handleReject(c); }} className="flex-1 px-2 py-1 text-xs rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors">✗ Reject</button>
                        <button onClick={e => { e.stopPropagation(); setSelectedCandidate(c); setGradForm({ position_size: 500, sl_pct: 6, tp_pct: 15, conviction_min: 74, notes: '' }); }} className="flex-1 px-2 py-1 text-xs rounded border border-green-500/30 text-green-400 hover:bg-green-500/10 transition-colors">✓ Review</button>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {selectedCandidate && (
                <div className="rounded-lg border border-blue-500/40 bg-blue-500/5 p-4 space-y-3 mt-3">
                  <div className="text-xs font-semibold text-blue-300">CIO Decision — {selectedCandidate.template_name} / {selectedCandidate.symbol}</div>
                  <div className="grid grid-cols-2 gap-3 text-xs">
                    <div><label className="text-gray-400 block mb-1">Virtual Order Size ($)</label>
                      <input type="number" min={200} max={1500} step={50} value={gradForm.position_size}
                        onChange={e => setGradForm(f => ({ ...f, position_size: Number(e.target.value) }))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs" />
                      <div className="text-gray-500 mt-0.5">Real: ${(gradForm.position_size * 0.10).toFixed(0)}</div>
                    </div>
                    <div><label className="text-gray-400 block mb-1">Conviction Min</label>
                      <input type="number" min={60} max={100} value={gradForm.conviction_min}
                        onChange={e => setGradForm(f => ({ ...f, conviction_min: Number(e.target.value) }))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs" />
                    </div>
                    <div><label className="text-gray-400 block mb-1">Stop Loss (%)</label>
                      <input type="number" min={1} max={20} step={0.5} value={gradForm.sl_pct}
                        onChange={e => setGradForm(f => ({ ...f, sl_pct: Number(e.target.value) }))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs" />
                    </div>
                    <div><label className="text-gray-400 block mb-1">Take Profit (%)</label>
                      <input type="number" min={1} max={50} step={0.5} value={gradForm.tp_pct}
                        onChange={e => setGradForm(f => ({ ...f, tp_pct: Number(e.target.value) }))}
                        className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs" />
                    </div>
                  </div>
                  <input type="text" placeholder="Notes (optional)" value={gradForm.notes}
                    onChange={e => setGradForm(f => ({ ...f, notes: e.target.value }))}
                    className="w-full bg-gray-800 border border-gray-600 rounded px-2 py-1 text-gray-200 text-xs" />
                  <div className="flex gap-2">
                    <button onClick={() => setSelectedCandidate(null)} className="flex-1 px-3 py-1.5 text-xs rounded border border-gray-600 text-gray-400 hover:bg-gray-800 transition-colors">Cancel</button>
                    <button onClick={handleApprove} disabled={gradSubmitting} className="flex-1 px-3 py-1.5 text-xs rounded bg-green-600 hover:bg-green-700 text-white font-semibold transition-colors disabled:opacity-50">
                      {gradSubmitting ? 'Approving...' : '✓ APPROVE → LIVE'}
                    </button>
                  </div>
                </div>
              )}

              {liveStrategies.length > 0 && (
                <>
                  <div className="text-xs font-medium text-gray-400 mt-4 mb-1">Active Live Authorizations ({liveStrategies.filter((ls: any) => !ls.retired_at).length})</div>
                  <div className="space-y-2">
                    {liveStrategies.filter((ls: any) => !ls.retired_at).map((ls: any) => (
                      <div key={ls.id} className="rounded-lg border border-green-500/20 bg-green-500/5 p-3 flex items-center justify-between">
                        <div>
                          <div className="text-xs font-semibold text-gray-200">{ls.template_name} / {ls.symbol}</div>
                          <div className="text-xs text-gray-500">${ls.position_size} virtual · SL {(ls.sl_pct * 100).toFixed(1)}% · {ls.live_trades} trades</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={cn('text-xs font-mono font-semibold', (ls.live_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>{formatCurrency(ls.live_pnl ?? 0)}</span>
                          <button onClick={async () => {
                            if (!window.confirm(`Retire ${ls.symbol} from live?`)) return;
                            try { await apiClient.retireLiveStrategy(ls.id); toast.success('Retired'); fetchGraduation(); } catch (err: any) { toast.error(err.message); }
                          }} className="px-2 py-0.5 text-xs rounded border border-red-500/30 text-red-400 hover:bg-red-500/10 transition-colors">Retire</button>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </TabsContent>

            {/* Divergence Tab */}
            <TabsContent value="divergence" className="p-2 space-y-3">
              <div className="text-xs text-gray-500 mb-2">
                Divergence = live Sharpe / paper Sharpe × 100%. Below 50% flags as underperforming.
                Requires closed live trades to compute.
              </div>
              {divergence.length === 0 ? (
                <div className="flex items-center justify-center h-32 text-xs text-gray-500">No live trades yet — divergence will appear after first live fills close.</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs font-mono table-dense">
                    <thead>
                      <tr className="border-b border-[var(--color-dark-border)] text-gray-500">
                        <th className="py-1.5 px-2 text-left">Template</th>
                        <th className="py-1.5 px-2 text-left">Symbol</th>
                        <th className="py-1.5 px-2 text-right">Paper Sharpe</th>
                        <th className="py-1.5 px-2 text-right">Live Sharpe</th>
                        <th className="py-1.5 px-2 text-right">Divergence</th>
                        <th className="py-1.5 px-2 text-right">Paper Trades</th>
                        <th className="py-1.5 px-2 text-right">Live Trades</th>
                        <th className="py-1.5 px-2 text-right">Live P&L</th>
                      </tr>
                    </thead>
                    <tbody>
                      {divergence.map((d: any) => (
                        <tr key={d.id} className={cn('border-b border-[var(--color-dark-border)]/30 hover:bg-gray-800/40', d.divergence_flag && 'bg-red-500/5')}>
                          <td className="py-1.5 px-2 text-gray-200 max-w-[140px] truncate">{d.template_name}</td>
                          <td className="py-1.5 px-2 text-gray-300 font-semibold">{d.symbol}</td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{d.paper_sharpe?.toFixed(2) ?? '—'}</td>
                          <td className="py-1.5 px-2 text-right text-gray-400">{d.live_sharpe?.toFixed(2) ?? '—'}</td>
                          <td className={cn('py-1.5 px-2 text-right font-semibold',
                            d.divergence_pct == null ? 'text-gray-500' :
                            d.divergence_pct < 50 ? 'text-red-400' :
                            d.divergence_pct < 80 ? 'text-yellow-400' : 'text-green-400')}>
                            {d.divergence_pct != null ? `${d.divergence_pct}%` : d.live_trades > 0 ? 'N/A' : '—'}
                            {d.divergence_flag && ' ⚠'}
                          </td>
                          <td className="py-1.5 px-2 text-right text-gray-500">{d.paper_trades}</td>
                          <td className="py-1.5 px-2 text-right text-gray-500">{d.live_trades}</td>
                          <td className={cn('py-1.5 px-2 text-right', (d.live_pnl ?? 0) >= 0 ? 'text-green-400' : 'text-red-400')}>
                            {d.live_pnl != null ? formatCurrency(d.live_pnl) : '—'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </TabsContent>

          </div>
        </Tabs>
      </div>
    </div>
  );

  const sidePanel = (
    <div className="flex flex-col h-full p-3 gap-3">
      <div className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Live Account</div>

      {/* Status pill */}
      <div className={cn('rounded-lg border p-3 text-center',
        liveEnabled ? 'border-green-500/40 bg-green-500/5' : 'border-gray-700/40 bg-gray-800/20')}>
        <div className={cn('text-sm font-mono font-bold', liveEnabled ? 'text-green-400' : 'text-gray-500')}>
          {liveEnabled ? '● LIVE ACTIVE' : '○ LIVE OFF'}
        </div>
        <div className="text-xs text-gray-500 mt-1">
          {liveEnabled ? 'Real fills firing for approved pairs' : 'Master switch disabled'}
        </div>
      </div>

      {/* Quick stats */}
      <div className="space-y-2 text-xs">
        {[
          { label: 'Virtual Balance', value: formatCurrency(summary?.virtual_balance ?? 0) },
          { label: 'Real Investment', value: formatCurrency((summary?.virtual_balance ?? 0) * mirror) },
          { label: 'Unrealized P&L (V)', value: formatCurrency(summary?.unrealized_pnl_virtual ?? 0), color: (summary?.unrealized_pnl_virtual ?? 0) >= 0 ? 'text-green-400' : 'text-red-400' },
          { label: 'Unrealized P&L (R)', value: formatCurrency(summary?.unrealized_pnl_real ?? 0), color: (summary?.unrealized_pnl_real ?? 0) >= 0 ? 'text-green-400' : 'text-red-400' },
          { label: 'Deployed Capital', value: `${summary?.deployed_pct ?? 0}%` },
          { label: 'Active Pairs', value: String(summary?.active_live_authorizations ?? 0) },
        ].map(s => (
          <div key={s.label} className="flex items-center justify-between border-b border-[var(--color-dark-border)]/20 pb-1">
            <span className="text-gray-500">{s.label}</span>
            <span className={cn('font-mono font-semibold', s.color ?? 'text-gray-200')}>{s.value}</span>
          </div>
        ))}
      </div>

      {/* Divergence alerts */}
      {divergence.filter((d: any) => d.divergence_flag).length > 0 && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/5 p-3">
          <div className="text-xs font-semibold text-red-400 mb-2">⚠ Divergence Alerts</div>
          {divergence.filter((d: any) => d.divergence_flag).map((d: any) => (
            <div key={d.id} className="text-xs text-gray-400 py-0.5">
              {d.symbol}: live {d.divergence_pct}% of paper
            </div>
          ))}
        </div>
      )}
    </div>
  );

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="● Live Trading"
        description="Agent Portfolio — $10K virtual / $1K real / 10% mirror"
        compact={true}
      >
        <ResizablePanelLayout
          layoutId="live-panels"
          direction="horizontal"
          panels={[
            { id: 'live-main', defaultSize: 65, minSize: 400, content: mainPanel },
            { id: 'live-side', defaultSize: 35, minSize: 250, content: sidePanel },
          ]}
        />
      </PageTemplate>
    </DashboardLayout>
  );
};
