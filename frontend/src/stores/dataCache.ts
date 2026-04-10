import { create } from 'zustand';
import type { AccountInfo, Position, Order } from '../types';

interface CacheEntry<T> {
  data: T;
  timestamp: number;
}

interface DataCacheStore {
  // Cached data
  accountInfo: CacheEntry<AccountInfo> | null;
  positions: CacheEntry<Position[]> | null;
  orders: CacheEntry<Order[]> | null;
  
  // Setters
  setAccountInfo: (data: AccountInfo) => void;
  setPositions: (data: Position[]) => void;
  setOrders: (data: Order[]) => void;
  
  // Getters with staleness check
  getAccountInfo: (maxAge: number) => AccountInfo | null;
  getPositions: (maxAge: number) => Position[] | null;
  getOrders: (maxAge: number) => Order[] | null;
  
  // Utility
  isStale: (key: 'accountInfo' | 'positions' | 'orders', maxAge: number) => boolean;
  clear: () => void;
  clearAll: () => void;
}

export const useDataCache = create<DataCacheStore>((set, get) => ({
  accountInfo: null,
  positions: null,
  orders: null,
  
  setAccountInfo: (data) => set({ accountInfo: { data, timestamp: Date.now() } }),
  setPositions: (data) => set({ positions: { data, timestamp: Date.now() } }),
  setOrders: (data) => set({ orders: { data, timestamp: Date.now() } }),
  
  getAccountInfo: (maxAge) => {
    const entry = get().accountInfo;
    if (!entry) return null;
    if (Date.now() - entry.timestamp > maxAge) return null;
    return entry.data;
  },
  
  getPositions: (maxAge) => {
    const entry = get().positions;
    if (!entry) return null;
    if (Date.now() - entry.timestamp > maxAge) return null;
    return entry.data;
  },
  
  getOrders: (maxAge) => {
    const entry = get().orders;
    if (!entry) return null;
    if (Date.now() - entry.timestamp > maxAge) return null;
    return entry.data;
  },
  
  isStale: (key, maxAge) => {
    const entry = get()[key];
    if (!entry) return true;
    return Date.now() - entry.timestamp > maxAge;
  },
  
  clear: () => set({ accountInfo: null, positions: null, orders: null }),
  
  clearAll: () => set({ accountInfo: null, positions: null, orders: null }),
}));

// Cache durations (in milliseconds)
export const CACHE_DURATIONS = {
  ACCOUNT_INFO: 30000,  // 30 seconds - changes rarely
  POSITIONS: 10000,     // 10 seconds - changes frequently
  ORDERS: 10000,        // 10 seconds - changes frequently
  STRATEGIES: 60000,    // 60 seconds - changes rarely
  SYSTEM_STATUS: 5000,  // 5 seconds - check frequently
};
