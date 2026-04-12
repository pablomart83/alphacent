import { type FC, useEffect, useState, useMemo, useCallback } from 'react';
import {
  Search, ChevronDown, ChevronUp,
  Eye, EyeOff, ToggleLeft, ToggleRight,
} from 'lucide-react';
import { Card, CardContent } from '../ui/Card';
import { Button } from '../ui/Button';
import { Input } from '../ui/Input';
import { Badge } from '../ui/Badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { cn, formatPercentage, formatCurrency } from '../../lib/utils';
import { apiClient } from '../../services/api';
import { toast } from 'sonner';

interface TemplateData {
  name: string;
  description: string;
  market_regimes: string[];
  indicators: string[];
  entry_rules: string[];
  exit_rules: string[];
  success_rate: number;
  usage_count: number;
  strategy_type: string | null;
  direction: string | null;
  asset_classes: string[] | null;
  expected_trade_frequency: string | null;
  expected_holding_period: string | null;
  risk_reward_ratio: number | null;
  enabled: boolean;
  active_strategies: number;
  total_strategies_ever: number;
  avg_sharpe: number | null;
  avg_win_rate: number | null;
  avg_return: number | null;
  total_trades_live: number;
  total_pnl: number | null;
  best_symbol: string | null;
  worst_symbol: string | null;
  last_proposed: string | null;
  last_activated: string | null;
  is_intraday: boolean;
  is_4h: boolean;
  interval: string | null;
  activated_count: number;
  traded_count: number;
  proposed_count: number;
  approved_count: number;
  strategy_category: string | null;
}

type SortField = 'name' | 'active_strategies' | 'avg_sharpe' | 'avg_win_rate' | 'total_pnl' | 'proposed_count' | 'success_rate' | 'approved_count' | 'traded_count';
type SortDir = 'asc' | 'desc';

interface TemplateManagerProps {
  category?: 'dsl' | 'alpha_edge' | 'all';
}

export const TemplateManager: FC<TemplateManagerProps> = ({ category = 'all' }) => {
  const [templates, setTemplates] = useState<TemplateData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [dirFilter, setDirFilter] = useState('all');
  const [intervalFilter, setIntervalFilter] = useState('all');
  const [assetFilter, setAssetFilter] = useState('all');
  const [enabledFilter, setEnabledFilter] = useState('all');
  const [sortField, setSortField] = useState<SortField>('active_strategies');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [detailTemplate, setDetailTemplate] = useState<TemplateData | null>(null);
  const [pendingToggles, setPendingToggles] = useState<Record<string, boolean>>({});

  const fetchTemplates = useCallback(async () => {
    try {
      const data = await apiClient.getStrategyTemplates();
      setTemplates(data.templates || []);
    } catch (e) {
      console.error('Failed to fetch templates:', e);
      toast.error('Failed to load templates');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchTemplates(); }, [fetchTemplates]);

  // Derived filter options
  const strategyTypes = useMemo(() => {
    const s = new Set<string>();
    templates.forEach(t => { if (t.strategy_type) s.add(t.strategy_type); });
    return Array.from(s).sort();
  }, [templates]);

  const assetClasses = useMemo(() => {
    const s = new Set<string>();
    templates.forEach(t => (t.asset_classes || []).forEach(a => s.add(a)));
    return Array.from(s).sort();
  }, [templates]);

  // Filtered + sorted templates
  const filtered = useMemo(() => {
    let list = templates.filter(t => {
      // Category filter (DSL vs AE)
      if (category === 'dsl' && t.strategy_category === 'alpha_edge') return false;
      if (category === 'alpha_edge' && t.strategy_category !== 'alpha_edge') return false;
      if (search && !t.name.toLowerCase().includes(search.toLowerCase()) &&
          !t.description.toLowerCase().includes(search.toLowerCase())) return false;
      if (typeFilter !== 'all' && t.strategy_type !== typeFilter) return false;
      if (dirFilter !== 'all' && t.direction !== dirFilter) return false;
      if (intervalFilter !== 'all' && t.interval !== intervalFilter) return false;
      if (assetFilter !== 'all' && !(t.asset_classes || []).includes(assetFilter)) return false;
      if (enabledFilter === 'enabled' && !getEffectiveEnabled(t)) return false;
      if (enabledFilter === 'disabled' && getEffectiveEnabled(t)) return false;
      return true;
    });
    list.sort((a, b) => {
      const av = getSortValue(a, sortField);
      const bv = getSortValue(b, sortField);
      if (av === bv) return 0;
      if (av === null || av === undefined) return 1;
      if (bv === null || bv === undefined) return -1;
      return sortDir === 'asc' ? (av < bv ? -1 : 1) : (av > bv ? -1 : 1);
    });
    return list;
  }, [templates, search, typeFilter, dirFilter, intervalFilter, assetFilter, enabledFilter, sortField, sortDir, pendingToggles, category]);

  function getEffectiveEnabled(t: TemplateData): boolean {
    return pendingToggles[t.name] !== undefined ? pendingToggles[t.name] : t.enabled;
  }

  function getSortValue(t: TemplateData, field: SortField): any {
    switch (field) {
      case 'name': return t.name.toLowerCase();
      case 'active_strategies': return t.active_strategies;
      case 'avg_sharpe': return t.avg_sharpe ?? -999;
      case 'avg_win_rate': return t.avg_win_rate ?? -999;
      case 'total_pnl': return t.total_pnl ?? -999;
      case 'proposed_count': return t.proposed_count;
      case 'approved_count': return t.approved_count;
      case 'traded_count': return t.traded_count;
      case 'success_rate': return t.success_rate;
      default: return 0;
    }
  }

  const handleToggle = (name: string) => {
    const current = getEffectiveEnabled({ name, enabled: templates.find(t => t.name === name)?.enabled ?? true } as TemplateData);
    const newVal = !current;
    setPendingToggles(prev => ({ ...prev, [name]: newVal }));
    apiClient.toggleTemplate(name, newVal).then(() => {
      setTemplates(prev => prev.map(t => t.name === name ? { ...t, enabled: newVal } : t));
      setPendingToggles(prev => { const n = { ...prev }; delete n[name]; return n; });
    }).catch(() => {
      setPendingToggles(prev => { const n = { ...prev }; delete n[name]; return n; });
      toast.error(`Failed to toggle ${name}`);
    });
  };

  const handleEnableAll = () => {
    const bulk: Record<string, boolean> = {};
    filtered.forEach(t => { bulk[t.name] = true; });
    apiClient.bulkToggleTemplates(bulk).then(() => {
      setTemplates(prev => prev.map(t => bulk[t.name] !== undefined ? { ...t, enabled: true } : t));
      toast.success(`Enabled ${Object.keys(bulk).length} templates`);
    }).catch(() => toast.error('Failed to enable all'));
  };

  const handleDisableAll = () => {
    const bulk: Record<string, boolean> = {};
    filtered.forEach(t => { bulk[t.name] = false; });
    apiClient.bulkToggleTemplates(bulk).then(() => {
      setTemplates(prev => prev.map(t => bulk[t.name] !== undefined ? { ...t, enabled: false } : t));
      toast.success(`Disabled ${Object.keys(bulk).length} templates`);
    }).catch(() => toast.error('Failed to disable all'));
  };

  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('desc'); }
  };

  const SortIcon: FC<{ field: SortField }> = ({ field }) => {
    if (sortField !== field) return <ChevronDown className="h-3 w-3 opacity-30" />;
    return sortDir === 'asc' ? <ChevronUp className="h-3 w-3 text-accent-green" /> : <ChevronDown className="h-3 w-3 text-accent-green" />;
  };

  // Summary stats — scoped to the current category (filtered list)
  const categoryTemplates = templates.filter(t => {
    if (category === 'dsl' && t.strategy_category === 'alpha_edge') return false;
    if (category === 'alpha_edge' && t.strategy_category !== 'alpha_edge') return false;
    return true;
  });
  const enabledCount = categoryTemplates.filter(t => getEffectiveEnabled(t)).length;
  const disabledCount = categoryTemplates.length - enabledCount;
  const totalActive = categoryTemplates.reduce((s, t) => s + t.active_strategies, 0);
  const totalPnl = categoryTemplates.reduce((s, t) => s + (t.total_pnl || 0), 0);
  const categoryLabel = category === 'alpha_edge' ? 'AE Templates' : category === 'dsl' ? 'DSL Templates' : 'Templates';

  if (loading) return (
    <div className="flex items-center justify-center py-20">
      <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-accent-green" />
    </div>
  );

  return (
    <div className="space-y-4">
      {/* Summary row */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        <Card><CardContent className="p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider">{categoryLabel}</div>
          <div className="text-xl font-mono font-bold text-gray-100">{categoryTemplates.length}</div>
          <div className="text-xs text-gray-500">{enabledCount} enabled · {disabledCount} disabled</div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Active Strategies</div>
          <div className="text-xl font-mono font-bold text-accent-green">{totalActive}</div>
          <div className="text-xs text-gray-500">from {categoryTemplates.filter(t => t.active_strategies > 0).length} templates</div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Total P&L</div>
          <div className={cn("text-xl font-mono font-bold", totalPnl >= 0 ? "text-accent-green" : "text-accent-red")}>
            {formatCurrency(totalPnl)}
          </div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Showing</div>
          <div className="text-xl font-mono font-bold text-gray-100">{filtered.length}</div>
          <div className="text-xs text-gray-500">of {templates.length} templates</div>
        </CardContent></Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3">
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500" />
              <Input placeholder="Search templates..." value={search} onChange={e => setSearch(e.target.value)}
                className="pl-9 bg-dark-bg border-dark-border text-sm h-9" />
            </div>
            <Select value={typeFilter} onValueChange={setTypeFilter}>
              <SelectTrigger className="w-[140px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Type" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Types</SelectItem>
                {strategyTypes.map(t => <SelectItem key={t} value={t}>{t.replace('_', ' ')}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={dirFilter} onValueChange={setDirFilter}>
              <SelectTrigger className="w-[120px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Direction" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="long">Long</SelectItem>
                <SelectItem value="short">Short</SelectItem>
              </SelectContent>
            </Select>
            <Select value={intervalFilter} onValueChange={setIntervalFilter}>
              <SelectTrigger className="w-[110px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Interval" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="1h">1H</SelectItem>
                <SelectItem value="4h">4H</SelectItem>
                <SelectItem value="1d">Daily</SelectItem>
              </SelectContent>
            </Select>
            <Select value={assetFilter} onValueChange={setAssetFilter}>
              <SelectTrigger className="w-[130px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Asset" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Assets</SelectItem>
                {assetClasses.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={enabledFilter} onValueChange={setEnabledFilter}>
              <SelectTrigger className="w-[120px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All</SelectItem>
                <SelectItem value="enabled">Enabled</SelectItem>
                <SelectItem value="disabled">Disabled</SelectItem>
              </SelectContent>
            </Select>
            <div className="flex gap-1 ml-auto">
              <Button size="sm" variant="outline" onClick={handleEnableAll} className="h-9 text-xs text-accent-green border-accent-green/30 hover:bg-accent-green/10">
                <Eye className="h-3 w-3 mr-1" /> Enable All
              </Button>
              <Button size="sm" variant="outline" onClick={handleDisableAll} className="h-9 text-xs text-gray-400 border-gray-600 hover:bg-gray-700">
                <EyeOff className="h-3 w-3 mr-1" /> Disable All
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-dark-border text-gray-500 text-xs uppercase tracking-wider">
                  <th className="px-3 py-2.5 text-left w-10">On</th>
                  <th className="px-3 py-2.5 text-left cursor-pointer select-none" onClick={() => toggleSort('name')}>
                    <span className="flex items-center gap-1">Template <SortIcon field="name" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-center">Type</th>
                  <th className="px-3 py-2.5 text-center">Dir</th>
                  <th className="px-3 py-2.5 text-center">TF</th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('active_strategies')}>
                    <span className="flex items-center justify-end gap-1">Active <SortIcon field="active_strategies" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('proposed_count')}>
                    <span className="flex items-center justify-end gap-1">Proposed <SortIcon field="proposed_count" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('approved_count')}>
                    <span className="flex items-center justify-end gap-1">Approved <SortIcon field="approved_count" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('traded_count')}>
                    <span className="flex items-center justify-end gap-1">Traded <SortIcon field="traded_count" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('avg_sharpe')}>
                    <span className="flex items-center justify-end gap-1">Sharpe <SortIcon field="avg_sharpe" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('avg_win_rate')}>
                    <span className="flex items-center justify-end gap-1">Win% <SortIcon field="avg_win_rate" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('total_pnl')}>
                    <span className="flex items-center justify-end gap-1">P&L <SortIcon field="total_pnl" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-center">Best</th>
                  <th className="px-3 py-2.5 text-center">Regimes</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(t => {
                  const enabled = getEffectiveEnabled(t);
                  return (
                    <tr key={t.name} className={cn(
                      "border-b border-dark-border/50 hover:bg-dark-surface/50 transition-colors",
                      !enabled && "opacity-40"
                    )}>
                      <td className="px-3 py-2">
                        <button onClick={() => handleToggle(t.name)} className="focus:outline-none" title={enabled ? 'Disable' : 'Enable'}>
                          {enabled
                            ? <ToggleRight className="h-5 w-5 text-accent-green" />
                            : <ToggleLeft className="h-5 w-5 text-gray-600" />
                          }
                        </button>
                      </td>
                      <td className="px-3 py-2">
                        <button onClick={() => setDetailTemplate(t)} className="text-left hover:text-accent-green transition-colors">
                          <div className="font-mono text-xs text-gray-200 truncate max-w-[220px]">{t.name}</div>
                          <div className="text-[10px] text-gray-500 truncate max-w-[220px]">{t.description}</div>
                        </button>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge className="text-[10px] bg-blue-500/15 text-blue-300 border-blue-500/20">
                          {(t.strategy_type || 'n/a').replace('_', ' ')}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <Badge className={cn("text-[10px]",
                          t.direction === 'short' ? "bg-red-500/15 text-red-300 border-red-500/20" : "bg-green-500/15 text-green-300 border-green-500/20"
                        )}>
                          {(t.direction || 'long').toUpperCase()}
                        </Badge>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className={cn("font-mono text-xs",
                          t.interval === '1h' ? "text-yellow-400" : t.interval === '4h' ? "text-orange-400" : "text-gray-400"
                        )}>
                          {t.interval || '1d'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-mono text-xs font-semibold", t.active_strategies > 0 ? "text-accent-green" : "text-gray-600")}>
                          {t.active_strategies}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right font-mono text-xs text-gray-400">{t.proposed_count}</td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-mono text-xs", t.approved_count > 0 ? "text-blue-400" : "text-gray-600")}>
                          {t.approved_count}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-mono text-xs font-semibold", t.traded_count > 0 ? "text-accent-green" : "text-gray-600")}>
                          {t.traded_count}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-mono text-xs", (t.avg_sharpe ?? 0) >= 1 ? "text-accent-green" : (t.avg_sharpe ?? 0) > 0 ? "text-gray-300" : "text-accent-red")}>
                          {t.avg_sharpe !== null ? t.avg_sharpe.toFixed(2) : '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className="font-mono text-xs text-gray-300">
                          {t.avg_win_rate !== null ? formatPercentage(t.avg_win_rate * 100) : '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-right">
                        <span className={cn("font-mono text-xs font-semibold",
                          (t.total_pnl ?? 0) > 0 ? "text-accent-green" : (t.total_pnl ?? 0) < 0 ? "text-accent-red" : "text-gray-600"
                        )}>
                          {t.total_pnl !== null ? formatCurrency(t.total_pnl) : '—'}
                        </span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <span className="font-mono text-xs text-gray-400">{t.best_symbol || '—'}</span>
                      </td>
                      <td className="px-3 py-2 text-center">
                        <div className="flex flex-wrap gap-0.5 justify-center">
                          {t.market_regimes.slice(0, 3).map(r => (
                            <span key={r} className="text-[10px] px-1 py-0.5 rounded bg-dark-bg text-gray-500 border border-dark-border/50">
                              {r.replace('_', ' ').replace('ranging ', '').replace('trending ', '').slice(0, 8)}
                            </span>
                          ))}
                          {t.market_regimes.length > 3 && <span className="text-[10px] text-gray-600">+{t.market_regimes.length - 3}</span>}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-gray-500">No templates match your filters</div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={!!detailTemplate} onOpenChange={() => setDetailTemplate(null)}>
        <DialogContent className="max-w-2xl bg-dark-surface border-dark-border text-gray-100 max-h-[85vh] overflow-y-auto">
          {detailTemplate && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <span className="font-mono text-lg">{detailTemplate.name}</span>
                  <button onClick={() => handleToggle(detailTemplate.name)}>
                    {getEffectiveEnabled(detailTemplate)
                      ? <ToggleRight className="h-5 w-5 text-accent-green" />
                      : <ToggleLeft className="h-5 w-5 text-gray-600" />
                    }
                  </button>
                </DialogTitle>
              </DialogHeader>
              <p className="text-sm text-gray-400 mt-1">{detailTemplate.description}</p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Direction</div>
                  <div className={cn("font-mono text-sm font-bold", detailTemplate.direction === 'short' ? "text-red-400" : "text-green-400")}>
                    {(detailTemplate.direction || 'long').toUpperCase()}
                  </div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Interval</div>
                  <div className="font-mono text-sm font-bold text-gray-200">{detailTemplate.interval || '1d'}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">R:R Ratio</div>
                  <div className="font-mono text-sm font-bold text-gray-200">{detailTemplate.risk_reward_ratio?.toFixed(1) || '—'}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Type</div>
                  <div className="font-mono text-sm font-bold text-blue-300">{(detailTemplate.strategy_type || 'n/a').replace('_', ' ')}</div>
                </div>
              </div>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-3">
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Active Now</div>
                  <div className="font-mono text-lg font-bold text-accent-green">{detailTemplate.active_strategies}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Avg Sharpe</div>
                  <div className="font-mono text-lg font-bold text-gray-200">{detailTemplate.avg_sharpe?.toFixed(2) || '—'}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Win Rate</div>
                  <div className="font-mono text-lg font-bold text-gray-200">
                    {detailTemplate.avg_win_rate !== null ? formatPercentage(detailTemplate.avg_win_rate * 100) : '—'}
                  </div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-[10px] text-gray-500 uppercase">Total P&L</div>
                  <div className={cn("font-mono text-lg font-bold",
                    (detailTemplate.total_pnl ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"
                  )}>
                    {detailTemplate.total_pnl !== null ? formatCurrency(detailTemplate.total_pnl) : '—'}
                  </div>
                </div>
              </div>

              <div className="mt-4 space-y-3">
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">Entry Conditions</div>
                  <div className="space-y-1">
                    {detailTemplate.entry_rules.map((r, i) => (
                      <div key={i} className="text-xs font-mono bg-dark-bg rounded px-2 py-1 border border-dark-border text-green-300">{r}</div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">Exit Conditions</div>
                  <div className="space-y-1">
                    {detailTemplate.exit_rules.map((r, i) => (
                      <div key={i} className="text-xs font-mono bg-dark-bg rounded px-2 py-1 border border-dark-border text-red-300">{r}</div>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-xs text-gray-500 uppercase mb-1">Indicators</div>
                  <div className="flex flex-wrap gap-1">
                    {detailTemplate.indicators.map((ind, i) => (
                      <Badge key={i} className="text-[10px] bg-purple-500/15 text-purple-300 border-purple-500/20">{ind}</Badge>
                    ))}
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs text-gray-500 uppercase mb-1">Market Regimes</div>
                    <div className="flex flex-wrap gap-1">
                      {detailTemplate.market_regimes.map(r => (
                        <Badge key={r} className="text-[10px] bg-dark-bg text-gray-400 border-dark-border">{r.replace('_', ' ')}</Badge>
                      ))}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-500 uppercase mb-1">Asset Classes</div>
                    <div className="flex flex-wrap gap-1">
                      {(detailTemplate.asset_classes || []).map(a => (
                        <Badge key={a} className="text-[10px] bg-dark-bg text-gray-400 border-dark-border">{a}</Badge>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="grid grid-cols-3 gap-3 text-xs text-gray-500">
                  <div>Trade Freq: <span className="text-gray-300">{detailTemplate.expected_trade_frequency || '—'}</span></div>
                  <div>Hold Period: <span className="text-gray-300">{detailTemplate.expected_holding_period || '—'}</span></div>
                  <div>Best Symbol: <span className="text-accent-green font-mono">{detailTemplate.best_symbol || '—'}</span></div>
                </div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
