import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface Position {
  id: string;
  symbol: string;
  quantity: number;
  entryPrice: number;
  currentPrice: number;
  pnl: number;
  pnlPercent: number;
}

interface Order {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  quantity: number;
  price: number;
  status: string;
  timestamp: string;
}

interface TradingState {
  // Trading mode
  mode: 'DEMO' | 'LIVE';
  setMode: (mode: 'DEMO' | 'LIVE') => void;
  
  // Positions
  positions: Position[];
  setPositions: (positions: Position[]) => void;
  
  // Orders
  orders: Order[];
  setOrders: (orders: Order[]) => void;
  
  // Account balance
  balance: number;
  setBalance: (balance: number) => void;
  
  // WebSocket connection status
  wsConnected: boolean;
  setWsConnected: (connected: boolean) => void;
}

export const useTradingStore = create<TradingState>()(
  persist(
    (set) => ({
      mode: 'DEMO',
      setMode: (mode) => set({ mode }),
      
      positions: [],
      setPositions: (positions) => set({ positions }),
      
      orders: [],
      setOrders: (orders) => set({ orders }),
      
      balance: 0,
      setBalance: (balance) => set({ balance }),
      
      wsConnected: false,
      setWsConnected: (wsConnected) => set({ wsConnected }),
    }),
    {
      name: 'trading-storage',
      partialize: (state) => ({ mode: state.mode }), // Only persist mode
    }
  )
);
