import { create } from 'zustand';
import { apiClient } from '../../services/api';

export interface AuditLogEntry {
  id: string;
  timestamp: string;
  event_type: string;
  symbol?: string;
  strategy_name?: string;
  severity: 'info' | 'warning' | 'error';
  description: string;
  metadata?: Record<string, any>;
}

export interface AuditFilters {
  event_types: string[];
  symbol: string;
  strategy_name: string;
  severity: string;
  start_date: string;
  end_date: string;
  search: string;
}

export interface TradeLifecycleData {
  signal: { timestamp: string; conviction_score: number; signal_strength: number; indicators: Record<string, number> };
  risk_validation: { timestamp: string; position_size: number; checks_passed: string[]; checks_failed: string[] };
  order: { timestamp: string; expected_price: number; type: string; quantity: number };
  fill: { timestamp: string; fill_price: number; slippage: number };
  position: { opened_at: string; stop_loss: number; take_profit: number };
  trailing_stops: Array<{ timestamp: string; old_level: number; new_level: number }>;
  close: { timestamp: string; exit_reason: string; final_pnl: number; final_pnl_pct: number } | null;
}

interface AuditState {
  entries: AuditLogEntry[];
  totalCount: number;
  loading: boolean;
  error: string | null;
  filters: AuditFilters;
  offset: number;
  hasMore: boolean;
  tradeLifecycle: TradeLifecycleData | null;
  tradeLifecycleLoading: boolean;

  setFilter: (key: keyof AuditFilters, value: any) => void;
  resetFilters: () => void;
  fetch: () => Promise<void>;
  loadMore: () => Promise<void>;
  fetchTradeLifecycle: (tradeId: string) => Promise<void>;
  exportCsv: () => Promise<void>;
}

const defaultFilters: AuditFilters = {
  event_types: [],
  symbol: '',
  strategy_name: '',
  severity: '',
  start_date: '',
  end_date: '',
  search: '',
};

export const useAuditStore = create<AuditState>((set, get) => ({
  entries: [],
  totalCount: 0,
  loading: false,
  error: null,
  filters: { ...defaultFilters },
  offset: 0,
  hasMore: true,
  tradeLifecycle: null,
  tradeLifecycleLoading: false,

  setFilter: (key, value) => {
    set((s) => ({ filters: { ...s.filters, [key]: value }, offset: 0, entries: [], hasMore: true }));
  },

  resetFilters: () => {
    set({ filters: { ...defaultFilters }, offset: 0, entries: [], hasMore: true });
  },

  fetch: async () => {
    const { filters } = get();
    set({ loading: true, error: null, offset: 0 });
    try {
      const result = await apiClient.getAuditLog({
        event_types: filters.event_types.length ? filters.event_types : undefined,
        symbol: filters.symbol || undefined,
        strategy_name: filters.strategy_name || undefined,
        severity: filters.severity || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        search: filters.search || undefined,
        offset: 0,
        limit: 100,
      });
      const entries = result?.entries ?? result?.data ?? [];
      const total = result?.total_count ?? entries.length;
      set({ entries, totalCount: total, loading: false, offset: entries.length, hasMore: entries.length < total });
    } catch (err: any) {
      set({ error: err?.message || 'Failed to load audit log', loading: false, entries: [] });
    }
  },

  loadMore: async () => {
    const { filters, offset, hasMore, loading } = get();
    if (!hasMore || loading) return;
    set({ loading: true });
    try {
      const result = await apiClient.getAuditLog({
        event_types: filters.event_types.length ? filters.event_types : undefined,
        symbol: filters.symbol || undefined,
        strategy_name: filters.strategy_name || undefined,
        severity: filters.severity || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        search: filters.search || undefined,
        offset,
        limit: 100,
      });
      const newEntries = result?.entries ?? result?.data ?? [];
      const total = result?.total_count ?? 0;
      set((s) => ({
        entries: [...s.entries, ...newEntries],
        offset: s.offset + newEntries.length,
        hasMore: s.offset + newEntries.length < total,
        loading: false,
      }));
    } catch {
      set({ loading: false });
    }
  },

  fetchTradeLifecycle: async (tradeId: string) => {
    set({ tradeLifecycleLoading: true, tradeLifecycle: null });
    try {
      const data = await apiClient.getTradeLifecycle(tradeId);
      set({ tradeLifecycle: data, tradeLifecycleLoading: false });
    } catch {
      set({ tradeLifecycleLoading: false });
    }
  },

  exportCsv: async () => {
    const { filters } = get();
    try {
      const blob = await apiClient.exportAuditLog({
        event_types: filters.event_types.length ? filters.event_types : undefined,
        symbol: filters.symbol || undefined,
        severity: filters.severity || undefined,
        start_date: filters.start_date || undefined,
        end_date: filters.end_date || undefined,
        search: filters.search || undefined,
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      const start = filters.start_date || 'all';
      const end = filters.end_date || 'now';
      a.href = url;
      a.download = `AlphaCent_AuditLog_${start}_${end}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      // handled by caller
    }
  },
}));
