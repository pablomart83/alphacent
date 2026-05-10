import { create } from 'zustand'
import { persist } from 'zustand/middleware'

/** Resizable panel layouts — persisted per layoutId. */

interface LayoutState {
  panelSizes: Record<string, number[]>
  fullscreen: Record<string, boolean>
  collapsed: Record<string, boolean>
  setPanelSizes: (id: string, sizes: number[]) => void
  setFullscreen: (id: string, value: boolean) => void
  setCollapsed: (id: string, value: boolean) => void
  toggleFullscreen: (id: string) => void
  toggleCollapsed: (id: string) => void
}

export const useLayoutStore = create<LayoutState>()(
  persist(
    (set, get) => ({
      panelSizes: {},
      fullscreen: {},
      collapsed: {},
      setPanelSizes: (id, sizes) =>
        set({ panelSizes: { ...get().panelSizes, [id]: sizes } }),
      setFullscreen: (id, value) =>
        set({ fullscreen: { ...get().fullscreen, [id]: value } }),
      setCollapsed: (id, value) =>
        set({ collapsed: { ...get().collapsed, [id]: value } }),
      toggleFullscreen: (id) =>
        set({
          fullscreen: { ...get().fullscreen, [id]: !get().fullscreen[id] },
        }),
      toggleCollapsed: (id) =>
        set({
          collapsed: { ...get().collapsed, [id]: !get().collapsed[id] },
        }),
    }),
    {
      name: 'alphacent.layout',
    },
  ),
)
