import { type FC, useEffect, useState, useMemo, useCallback } from 'react';
import {
  Search, ChevronDown, ChevronUp,
} from 'lucide-react';
import { Card, CardContent } from '../ui/Card';
import { Input } from '../ui/Input';
import { Badge } from '../ui/Badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../ui/select';
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '../ui/dialog';
import { cn, formatPercentage, formatCurrency } from '../../lib/utils';
import { apiClient } from '../../services/api';
import { toast } from 'sonner';

interface SymbolData {
  symbol: string;
  asset_class: string;
  sector: string;
  active_strategies: number;
  activated_count: number;
  traded_count: number;
  usage_count: number;
  avg_sharpe: number | null;
  avg_win_rate: number | null;
  total_pnl: number | null;
  total_trades_live: number;
  open_positions: number;
  best_template: string | null;
  worst_template: string | null;
  last_signal: string | null;
  last_trade: string | null;
}

type SortField = 'symbol' | 'active_strategies' | 'activated_count' | 'traded_count' | 'usage_count' | 'avg_sharpe' | 'avg_win_rate' | 'total_pnl' | 'open_positions';
type SortDir = 'asc' | 'desc';

export const SymbolManager: FC = () => {
  const [symbols, setSymbols] = useState<SymbolData[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [assetFilter, setAssetFilter] = useState('all');
  const [sectorFilter, setSectorFilter] = useState('all');
  const [sortField, setSortField] = useState<SortField>('total_pnl');
  const [sortDir, setSortDir] = useState<SortDir>('desc');
  const [detailSymbol, setDetailSymbol] = useState<SymbolData | null>(null);

  const fetchSymbols = useCallback(async () => {
    try {
      const data = await apiClient.getSymbolStats();
      setSymbols(data.symbols || []);
    } catch (e) {
      console.error('Failed to fetch symbol stats:', e);
      toast.error('Failed to load symbol stats');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchSymbols(); }, [fetchSymbols]);

  const assetClasses = useMemo(() => {
    const s = new Set<string>();
    symbols.forEach(sym => s.add(sym.asset_class));
    return Array.from(s).sort();
  }, [symbols]);

  const sectors = useMemo(() => {
    const s = new Set<string>();
    symbols.forEach(sym => s.add(sym.sector));
    return Array.from(s).sort();
  }, [symbols]);

  const filtered = useMemo(() => {
    let list = symbols.filter(s => {
      if (search && !s.symbol.toLowerCase().includes(search.toLowerCase()) &&
          !s.sector.toLowerCase().includes(search.toLowerCase())) return false;
      if (assetFilter !== 'all' && s.asset_class !== assetFilter) return false;
      if (sectorFilter !== 'all' && s.sector !== sectorFilter) return false;
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
  }, [symbols, search, assetFilter, sectorFilter, sortField, sortDir]);

  function getSortValue(s: SymbolData, field: SortField): any {
    switch (field) {
      case 'symbol': return s.symbol.toLowerCase();
      case 'active_strategies': return s.active_strategies;
      case 'activated_count': return s.activated_count;
      case 'traded_count': return s.traded_count;
      case 'usage_count': return s.usage_count;
      case 'avg_sharpe': return s.avg_sharpe ?? -999;
      case 'avg_win_rate': return s.avg_win_rate ?? -999;
      case 'total_pnl': return s.total_pnl ?? -999;
      case 'open_positions': return s.open_positions;
      default: return 0;
    }
  }

  const toggleSort = (field: SortField) => {
    if (sortField === field) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('desc'); }
  };

  const SortIcon: FC<{ field: SortField }> = ({ field }) => {
    if (sortField !== field) return <ChevronDown className="h-3 w-3 opacity-30" />;
    return sortDir === 'asc' ? <ChevronUp className="h-3 w-3 text-accent-green" /> : <ChevronDown className="h-3 w-3 text-accent-green" />;
  };

  const totalPositions = symbols.reduce((s, sym) => s + sym.open_positions, 0);
  const totalPnl = symbols.reduce((s, sym) => s + (sym.total_pnl || 0), 0);
  const symbolsWithPositions = symbols.filter(s => s.open_positions > 0).length;

  const assetClassColor: Record<string, string> = {
    stock: 'bg-blue-500/15 text-blue-300 border-blue-500/20',
    etf: 'bg-purple-500/15 text-purple-300 border-purple-500/20',
    crypto: 'bg-orange-500/15 text-orange-300 border-orange-500/20',
    forex: 'bg-cyan-500/15 text-cyan-300 border-cyan-500/20',
    commodity: 'bg-yellow-500/15 text-yellow-300 border-yellow-500/20',
    index: 'bg-green-500/15 text-green-300 border-green-500/20',
  };

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
          <div className="text-xs text-gray-500 uppercase tracking-wider">Symbols</div>
          <div className="text-xl font-mono font-bold text-gray-100">{symbols.length}</div>
          <div className="text-xs text-gray-500">{symbolsWithPositions} with positions</div>
        </CardContent></Card>
        <Card><CardContent className="p-3">
          <div className="text-xs text-gray-500 uppercase tracking-wider">Open Positions</div>
          <div className="text-xl font-mono font-bold text-accent-green">{totalPositions}</div>
          <div className="text-xs text-gray-500">across {symbolsWithPositions} symbols</div>
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
          <div className="text-xs text-gray-500">of {symbols.length} symbols</div>
        </CardContent></Card>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-3">
          <div className="flex flex-wrap gap-2 items-center">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-gray-500" />
              <Input placeholder="Search symbols..." value={search} onChange={e => setSearch(e.target.value)}
                className="pl-9 bg-dark-bg border-dark-border text-sm h-9" />
            </div>
            <Select value={assetFilter} onValueChange={setAssetFilter}>
              <SelectTrigger className="w-[140px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Asset Class" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Assets</SelectItem>
                {assetClasses.map(a => <SelectItem key={a} value={a}>{a}</SelectItem>)}
              </SelectContent>
            </Select>
            <Select value={sectorFilter} onValueChange={setSectorFilter}>
              <SelectTrigger className="w-[160px] bg-dark-bg border-dark-border h-9 text-sm">
                <SelectValue placeholder="Sector" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Sectors</SelectItem>
                {sectors.map(s => <SelectItem key={s} value={s}>{s}</SelectItem>)}
              </SelectContent>
            </Select>
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
                  <th className="px-3 py-2.5 text-left cursor-pointer select-none" onClick={() => toggleSort('symbol')}>
                    <span className="flex items-center gap-1">Symbol <SortIcon field="symbol" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-center">Class</th>
                  <th className="px-3 py-2.5 text-center">Sector</th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('open_positions')}>
                    <span className="flex items-center justify-end gap-1">Positions <SortIcon field="open_positions" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('active_strategies')}>
                    <span className="flex items-center justify-end gap-1">Active <SortIcon field="active_strategies" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('usage_count')}>
                    <span className="flex items-center justify-end gap-1">Used <SortIcon field="usage_count" /></span>
                  </th>
                  <th className="px-3 py-2.5 text-right cursor-pointer select-none" onClick={() => toggleSort('activated_count')}>
                    <span className="flex items-center justify-end gap-1">Activated <SortIcon field="activated_count" /></span>
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
                  <th className="px-3 py-2.5 text-center">Best Template</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(s => (
                  <tr key={s.symbol} className="border-b border-dark-border/50 hover:bg-dark-surface/50 transition-colors">
                    <td className="px-3 py-2">
                      <button onClick={() => setDetailSymbol(s)} className="text-left hover:text-accent-green transition-colors">
                        <div className="font-mono text-xs font-bold text-gray-200">{s.symbol}</div>
                      </button>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <Badge className={cn("text-xs", assetClassColor[s.asset_class] || "bg-gray-500/15 text-gray-300 border-gray-500/20")}>
                        {s.asset_class}
                      </Badge>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="text-xs px-1 py-0.5 rounded bg-dark-bg text-gray-500 border border-dark-border/50">
                        {s.sector.slice(0, 12)}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs font-semibold", s.open_positions > 0 ? "text-accent-green" : "text-gray-600")}>
                        {s.open_positions}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs", s.active_strategies > 0 ? "text-blue-400" : "text-gray-600")}>
                        {s.active_strategies}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right font-mono text-xs text-gray-400">{s.usage_count}</td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs", s.activated_count > 0 ? "text-blue-400" : "text-gray-600")}>
                        {s.activated_count}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs font-semibold", s.traded_count > 0 ? "text-accent-green" : "text-gray-600")}>
                        {s.traded_count}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs", (s.avg_sharpe ?? 0) >= 1 ? "text-accent-green" : (s.avg_sharpe ?? 0) > 0 ? "text-gray-300" : "text-accent-red")}>
                        {s.avg_sharpe !== null ? s.avg_sharpe.toFixed(2) : '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className="font-mono text-xs text-gray-300">
                        {s.avg_win_rate !== null ? formatPercentage(s.avg_win_rate * 100) : '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-right">
                      <span className={cn("font-mono text-xs font-semibold",
                        (s.total_pnl ?? 0) > 0 ? "text-accent-green" : (s.total_pnl ?? 0) < 0 ? "text-accent-red" : "text-gray-600"
                      )}>
                        {s.total_pnl !== null ? formatCurrency(s.total_pnl) : '—'}
                      </span>
                    </td>
                    <td className="px-3 py-2 text-center">
                      <span className="font-mono text-xs text-gray-400">{s.best_template?.slice(0, 20) || '—'}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {filtered.length === 0 && (
              <div className="text-center py-12 text-gray-500">No symbols match your filters</div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Detail Dialog */}
      <Dialog open={!!detailSymbol} onOpenChange={() => setDetailSymbol(null)}>
        <DialogContent className="max-w-lg bg-dark-surface border-dark-border text-gray-100 max-h-[85vh] overflow-y-auto">
          {detailSymbol && (
            <>
              <DialogHeader>
                <DialogTitle className="flex items-center gap-3">
                  <span className="font-mono text-lg">{detailSymbol.symbol}</span>
                  <Badge className={cn("text-xs", assetClassColor[detailSymbol.asset_class] || "bg-gray-500/15 text-gray-300")}>
                    {detailSymbol.asset_class}
                  </Badge>
                </DialogTitle>
              </DialogHeader>
              <p className="text-sm text-gray-400 mt-1">Sector: {detailSymbol.sector}</p>

              <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4">
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Open Positions</div>
                  <div className="font-mono text-lg font-bold text-accent-green">{detailSymbol.open_positions}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Active Strategies</div>
                  <div className="font-mono text-lg font-bold text-blue-400">{detailSymbol.active_strategies}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Avg Sharpe</div>
                  <div className="font-mono text-lg font-bold text-gray-200">{detailSymbol.avg_sharpe?.toFixed(2) || '—'}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Total P&L</div>
                  <div className={cn("font-mono text-lg font-bold",
                    (detailSymbol.total_pnl ?? 0) >= 0 ? "text-accent-green" : "text-accent-red"
                  )}>
                    {detailSymbol.total_pnl !== null ? formatCurrency(detailSymbol.total_pnl) : '—'}
                  </div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3 mt-3">
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Used</div>
                  <div className="font-mono text-sm font-bold text-gray-400">{detailSymbol.usage_count}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Activated</div>
                  <div className="font-mono text-sm font-bold text-blue-400">{detailSymbol.activated_count}</div>
                </div>
                <div className="bg-dark-bg rounded p-2.5 border border-dark-border">
                  <div className="text-xs text-gray-500 uppercase">Traded</div>
                  <div className="font-mono text-sm font-bold text-accent-green">{detailSymbol.traded_count}</div>
                </div>
              </div>

              <div className="mt-4 space-y-2 text-xs text-gray-500">
                <div>Win Rate: <span className="text-gray-300 font-mono">{detailSymbol.avg_win_rate !== null ? formatPercentage(detailSymbol.avg_win_rate * 100) : '—'}</span></div>
                <div>Live Trades: <span className="text-gray-300 font-mono">{detailSymbol.total_trades_live}</span></div>
                <div>Best Template: <span className="text-accent-green font-mono">{detailSymbol.best_template || '—'}</span></div>
                <div>Worst Template: <span className="text-accent-red font-mono">{detailSymbol.worst_template || '—'}</span></div>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </div>
  );
};
