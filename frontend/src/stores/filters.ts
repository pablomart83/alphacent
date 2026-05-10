import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Per-page filter state, keyed by surface + tab (e.g. "book.positions"). */

type FilterValue = string | number | boolean | string[] | null

interface FiltersState {
  filters: Record<string, Record<string, FilterValue>>
  setFilter: (key: string, name: string, value: FilterValue) => void
  setFilters: (key: string, values: Record<string, FilterValue>) => void
  clearFilters: (key: string) => void
  getFilters: (key: string) => Record<string, FilterValue>
}

export const useFiltersStore = create<FiltersState>()(
  persist(
    (set, get) => ({
      filters: {},
      setFilter: (key, name, value) => {
        const current = get().filters[key] || {}
        set({ filters: { ...get().filters, [key]: { ...current, [name]: value } } })
      },
      setFilters: (key, values) => {
        set({ filters: { ...get().filters, [key]: values } })
      },
      clearFilters: (key) => {
        const { [key]: _removed, ...rest } = get().filters
        void _removed
        set({ filters: rest })
      },
      getFilters: (key) => get().filters[key] || {},
    }),
    {
      name: 'alphacent.filters',
    },
  ),
)
