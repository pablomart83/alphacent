import { create } from 'zustand'

/**
 * Ephemeral UI overlays (drawers, help dialogs) that don't need
 * persistence but do need cross-component access.
 */
interface UiOverlaysState {
  notificationsOpen: boolean
  shortcutHelpOpen: boolean
  setNotificationsOpen: (v: boolean) => void
  setShortcutHelpOpen: (v: boolean) => void
  toggleNotifications: () => void
  toggleShortcutHelp: () => void
}

export const useUiOverlays = create<UiOverlaysState>((set, get) => ({
  notificationsOpen: false,
  shortcutHelpOpen: false,
  setNotificationsOpen: (v) => set({ notificationsOpen: v }),
  setShortcutHelpOpen: (v) => set({ shortcutHelpOpen: v }),
  toggleNotifications: () => set({ notificationsOpen: !get().notificationsOpen }),
  toggleShortcutHelp: () => set({ shortcutHelpOpen: !get().shortcutHelpOpen }),
}))
