import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type TradingMode = 'DEMO' | 'LIVE'

interface TradingModeState {
  mode: TradingMode
  setMode: (mode: TradingMode) => void
  toggle: () => void
}

export const useTradingMode = create<TradingModeState>()(
  persist(
    (set, get) => ({
      mode: 'DEMO',
      setMode: (mode) => set({ mode }),
      toggle: () => set({ mode: get().mode === 'DEMO' ? 'LIVE' : 'DEMO' }),
    }),
    {
      name: 'alphacent.trading-mode',
    },
  ),
)
