import { create } from 'zustand';
import { apiClient } from '../../services/api';

export interface CircuitBreaker {
  category: string;
  state: 'CLOSED' | 'OPEN' | 'HALF_OPEN' | 'closed' | 'open' | 'half_open';
  failure_count: number;
  cooldown_remaining_seconds: number;
}

export interface SubTask {
  name: string;
  last_cycle: string;
  status: 'healthy' | 'stale' | 'error';
  interval_seconds: number;
}

export interface SystemHealthData {
  circuit_breakers: CircuitBreaker[];
  monitoring_service: {
    running: boolean;
    sub_tasks: SubTask[];
  };
  trading_scheduler: {
    last_signal_time: string;
    next_expected_run: string;
    signals_last_run: number;
    orders_last_run: number;
  };
  etoro_api: {
    requests_per_minute: number;
    error_rate_5m: number;
    avg_response_ms: number;
    rate_limit_remaining: number;
  };
  cache_stats: {
    order_cache_hit_rate: number;
    position_cache_hit_rate: number;
    historical_cache_hit_rate: number;
    fmp_cache_warm_status: {
      last_warm_time: string;
      symbols_from_api: number;
      symbols_from_cache: number;
    };
  };
  events_24h: Array<{
    timestamp: string;
    type: string;
    description: string;
    severity: 'info' | 'warning' | 'error';
  }>;
}

interface SystemHealthState {
  data: SystemHealthData | null;
  loading: boolean;
  error: string | null;
  lastFetchedAt: Date | null;
  fetch: () => Promise<void>;
}

export const useSystemHealthStore = create<SystemHealthState>((set) => ({
  data: null,
  loading: false,
  error: null,
  lastFetchedAt: null,

  fetch: async () => {
    set({ loading: true, error: null });
    try {
      const data = await apiClient.getSystemHealth();
      set({ data, loading: false, lastFetchedAt: new Date() });
    } catch (err: any) {
      set({ error: err?.message || 'Failed to load system health', loading: false });
    }
  },
}));
