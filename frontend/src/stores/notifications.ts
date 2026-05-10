import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export type NotificationSeverity = 'info' | 'success' | 'warning' | 'error'

export interface AutonomousNotification {
  id: string
  type: string
  severity: NotificationSeverity
  title: string
  message: string
  timestamp: string
  read: boolean
  data?: unknown
  actionButton?: { label: string; action: string; url?: string }
}

interface NotificationsState {
  items: AutonomousNotification[]
  unreadCount: number
  add: (n: AutonomousNotification) => void
  markAsRead: (id: string) => void
  markAllRead: () => void
  clear: (id: string) => void
  clearAll: () => void
}

const MAX_NOTIFICATIONS = 100

export const useNotificationsStore = create<NotificationsState>()(
  persist(
    (set, get) => ({
      items: [],
      unreadCount: 0,
      add: (n) => {
        const existing = get().items
        if (existing.some((x) => x.id === n.id)) return
        const next = [n, ...existing].slice(0, MAX_NOTIFICATIONS)
        set({ items: next, unreadCount: next.filter((x) => !x.read).length })
      },
      markAsRead: (id) => {
        const next = get().items.map((x) => (x.id === id ? { ...x, read: true } : x))
        set({ items: next, unreadCount: next.filter((x) => !x.read).length })
      },
      markAllRead: () => {
        const next = get().items.map((x) => ({ ...x, read: true }))
        set({ items: next, unreadCount: 0 })
      },
      clear: (id) => {
        const next = get().items.filter((x) => x.id !== id)
        set({ items: next, unreadCount: next.filter((x) => !x.read).length })
      },
      clearAll: () => set({ items: [], unreadCount: 0 }),
    }),
    {
      name: 'alphacent.notifications',
    },
  ),
)
