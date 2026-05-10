import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface CommandPaletteState {
  open: boolean
  recentCommands: string[]
  setOpen: (open: boolean) => void
  toggle: () => void
  pushRecent: (id: string) => void
}

export const useCommandPalette = create<CommandPaletteState>()(
  persist(
    (set, get) => ({
      open: false,
      recentCommands: [],
      setOpen: (open) => set({ open }),
      toggle: () => set({ open: !get().open }),
      pushRecent: (id) => {
        const list = [id, ...get().recentCommands.filter((r) => r !== id)].slice(0, 10)
        set({ recentCommands: list })
      },
    }),
    {
      name: 'alphacent.command-palette',
      partialize: (s) => ({ recentCommands: s.recentCommands }),
    },
  ),
)
