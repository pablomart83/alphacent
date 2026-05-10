import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type ResearchPeriod = '1W' | '1M' | '3M' | '6M' | '1Y' | 'ALL'
export type ResearchInterval = '1d' | '4h' | '1h'

interface ResearchState {
  period: ResearchPeriod
  interval: ResearchInterval
  setPeriod: (p: ResearchPeriod) => void
  setInterval: (i: ResearchInterval) => void
}

export const useResearchStore = create<ResearchState>()(
  persist(
    (set) => ({
      period: '3M',
      interval: '1d',
      setPeriod: (period) => set({ period }),
      setInterval: (interval) => set({ interval }),
    }),
    {
      name: 'alphacent.research',
    },
  ),
)
