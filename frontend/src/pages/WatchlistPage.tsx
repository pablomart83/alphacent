import { type FC, useEffect, useState, useCallback, useMemo } from 'react';
import { motion } from 'framer-motion';
import { Search, RefreshCw, AlertCircle, Eye } from 'lucide-react';
import { DashboardLayout } from '../components/DashboardLayout';
import { PageTemplate } from '../components/PageTemplate';
import { DataTable } from '../components/trading/DataTable';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../components/ui/select';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { wsManager } from '../services/websocket';
import { cn, formatCurrency, formatPercentage } from '../lib/utils';
import { classifyError } from '../lib/errors';
import type { MarketData, Position } from '../types';
import { ColumnDef } from '@tanstack/react-table';
import { usePolling } from '../hooks/usePolling';
import { PageSkeleton, RefreshIndicator } from '../components/ui/skeleton';
import { DataFreshnessIndicator } from '../components/ui/DataFreshnessIndicator';

interface WatchlistPageProps {
  onLogout: () => void;
}

interface WatchlistRow {
  symbol: string;
  price: number;
  dailyChange: number;
  dailyChangePct: number;
  volume: number;
  assetClass: string;
}

// Simple asset class inference from symbol
function inferAssetClass(symbol: string): string {
  const s = symbol.toUpperCase();
  if (s.includes('/') || ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD'].includes(s)) return 'forex';
  if (s.endsWith('BTC') || s.endsWith('ETH') || ['BTC', 'ETH', 'XRP', 'SOL', 'ADA', 'DOGE', 'DOT', 'MATIC', 'AVAX', 'LINK'].includes(s)) return 'crypto';
  if (['SPY', 'QQQ', 'IWM', 'DIA', 'VTI', 'VOO', 'XLF', 'XLE', 'XLK', 'XLV', 'XLI', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC', 'GLD', 'SLV', 'TLT', 'HYG', 'EEM', 'EFA', 'ARKK', 'ARKG'].includes(s)) return 'etf';
  if (['^GSPC', '^DJI', '^IXIC', '^RUT', '^VIX', 'VIX'].includes(s)) return 'index';
  if (['GC=F', 'SI=F', 'CL=F', 'NG=F'].includes(s)) return 'commodity';
  return 'stock';
}

export const WatchlistPage: FC<WatchlistPageProps> = ({ onLogout }) => {
  const { tradingMode, isLoading: tradingModeLoading } = useTradingMode();

  const [rows, setRows] = useState<WatchlistRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastFetchedAt, setLastFetchedAt] = useState<Date | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState('');
  const [assetClassFilter, setAssetClassFilter] = useState<string>('all');

  // Fetch positions to build watchlist rows
  const fetchWatchlist = useCallback(async () => {
    if (!tradingMode) return;
    try {
      setError(null);
      const positions: Position[] = await apiClient.getPositions(tradingMode);
      const watchlistRows: WatchlistRow[] = positions.map((p) => ({
        symbol: p.symbol,
        price: p.current_price,
        dailyChange: p.unrealized_pnl,
        dailyChangePct: p.unrealized_pnl_percent,
        volume: 0,
        assetClass: inferAssetClass(p.symbol),
      }));

      // Deduplicate by symbol (keep first occurrence)
      const seen = new Set<string>();
      const deduped = watchlistRows.filter((r) => {
        if (seen.has(r.symbol)) return false;
        seen.add(r.symbol);
        return true;
      });

      setRows(deduped);
      setLastFetchedAt(new Date());
      setLoading(false);
    } catch (err) {
      const classified = classifyError(err, 'watchlist');
      setError(classified.message);
      setLoading(false);
    }
  }, [tradingMode]);

  // Polling at 30s
  const { isRefreshing: pollingRefreshing } = usePolling({
    fetchFn: fetchWatchlist,
    intervalMs: 30000,
    enabled: !!tradingMode && !tradingModeLoading,
  });

  // WebSocket real-time updates
  useEffect(() => {
    const unsubscribe = wsManager.onMarketData((data: MarketData) => {
      setRows((prev) => {
        const idx = prev.findIndex((r) => r.symbol === data.symbol);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = {
            ...updated[idx],
            price: data.price,
            dailyChange: data.change,
            dailyChangePct: data.change_percent,
            volume: data.volume,
          };
          return updated;
        }
        return prev;
      });
    });
    return () => { unsubscribe(); };
  }, []);

  // Filtered rows
  const filteredRows = useMemo(() => {
    return rows.filter((row) => {
      const matchesSearch = row.symbol.toLowerCase().includes(searchQuery.toLowerCase());
      const matchesAssetClass = assetClassFilter === 'all' || row.assetClass === assetClassFilter;
      return matchesSearch && matchesAssetClass;
    });
  }, [rows, searchQuery, assetClassFilter]);

  // Table columns
  const columns: ColumnDef<WatchlistRow>[] = [
    {
      accessorKey: 'symbol',
      header: 'Symbol',
      cell: ({ row }) => (
        <div className="font-mono font-semibold text-sm text-gray-200">{row.original.symbol}</div>
      ),
    },
    {
      accessorKey: 'price',
      header: () => <div className="text-right">Price</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-sm">{formatCurrency(row.original.price)}</div>
      ),
    },
    {
      accessorKey: 'dailyChange',
      header: () => <div className="text-right">Change ($)</div>,
      cell: ({ row }) => (
        <div className={cn(
          'text-right font-mono text-sm font-semibold',
          row.original.dailyChange >= 0 ? 'text-accent-green' : 'text-accent-red'
        )}>
          {row.original.dailyChange >= 0 ? '+' : ''}{formatCurrency(row.original.dailyChange)}
        </div>
      ),
    },
    {
      accessorKey: 'dailyChangePct',
      header: () => <div className="text-right">Change (%)</div>,
      cell: ({ row }) => (
        <div className={cn(
          'text-right font-mono text-sm font-semibold',
          row.original.dailyChangePct >= 0 ? 'text-accent-green' : 'text-accent-red'
        )}>
          {row.original.dailyChangePct >= 0 ? '+' : ''}{formatPercentage(row.original.dailyChangePct)}
        </div>
      ),
    },
    {
      accessorKey: 'volume',
      header: () => <div className="text-right">Volume</div>,
      cell: ({ row }) => (
        <div className="text-right font-mono text-sm text-gray-400">
          {row.original.volume > 0 ? row.original.volume.toLocaleString() : '—'}
        </div>
      ),
    },
    {
      accessorKey: 'assetClass',
      header: 'Asset Class',
      cell: ({ row }) => (
        <span className="px-2 py-0.5 rounded text-xs font-mono bg-gray-500/20 text-gray-300 capitalize">
          {row.original.assetClass}
        </span>
      ),
    },
  ];

  if (tradingModeLoading || loading) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Watchlist" description="Market overview sourced from open positions">
          <PageSkeleton />
        </PageTemplate>
      </DashboardLayout>
    );
  }

  if (error && rows.length === 0) {
    return (
      <DashboardLayout onLogout={onLogout}>
        <PageTemplate title="◆ Watchlist" description="Market overview sourced from open positions">
          <div className="flex flex-col items-center justify-center h-64 gap-4">
            <AlertCircle className="h-8 w-8 text-accent-red" />
            <div className="text-gray-400 font-mono">Failed to load watchlist</div>
            <p className="text-sm text-muted-foreground">{error}</p>
            <Button variant="outline" size="sm" onClick={fetchWatchlist}>Retry</Button>
          </div>
        </PageTemplate>
      </DashboardLayout>
    );
  }

  const headerActions = (
    <div className="flex items-center gap-1.5">
      <DataFreshnessIndicator lastFetchedAt={lastFetchedAt} />
      <button onClick={fetchWatchlist} disabled={pollingRefreshing} className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors" title="Refresh">
        <RefreshCw className={cn('h-3.5 w-3.5', pollingRefreshing && 'animate-spin')} />
      </button>
    </div>
  );

  return (
    <DashboardLayout onLogout={onLogout}>
      <PageTemplate
        title="◆ Watchlist"
        description="Market overview sourced from open positions"
        actions={headerActions}
      >
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.3 }}
        className="p-4 sm:p-6 max-w-[1600px] mx-auto relative"
      >
        <RefreshIndicator visible={pollingRefreshing && !loading} />

        {/* Filters */}
        <Card className="mb-6">
          <CardContent className="pt-6">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <div className="relative lg:col-span-2">
                <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-4 w-4 text-gray-500" />
                <Input
                  placeholder="Search by symbol..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                  className="pl-10"
                />
              </div>
              <Select value={assetClassFilter} onValueChange={setAssetClassFilter}>
                <SelectTrigger>
                  <SelectValue placeholder="Asset Class" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Asset Classes</SelectItem>
                  <SelectItem value="stock">Stocks</SelectItem>
                  <SelectItem value="etf">ETFs</SelectItem>
                  <SelectItem value="forex">Forex</SelectItem>
                  <SelectItem value="index">Indices</SelectItem>
                  <SelectItem value="commodity">Commodities</SelectItem>
                  <SelectItem value="crypto">Crypto</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </CardContent>
        </Card>

        {/* Table */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              <span className="flex items-center gap-2">
                <Eye className="h-5 w-5" />
                Market Data
              </span>
              <span className="text-sm font-mono text-gray-400">
                {filteredRows.length} of {rows.length} symbols
              </span>
            </CardTitle>
          </CardHeader>
          <CardContent>
            <DataTable columns={columns} data={filteredRows} pageSize={25} />
            {rows.length > 0 && (
              <p className="text-xs text-gray-500 mt-4 font-mono">
                Data sourced from open positions. Change values reflect unrealized P&L. Real-time updates via WebSocket.
              </p>
            )}
          </CardContent>
        </Card>
      </motion.div>
      </PageTemplate>
    </DashboardLayout>
  );
};
