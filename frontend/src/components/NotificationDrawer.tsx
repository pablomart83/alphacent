import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { Bell, CheckCheck, CircleAlert, CircleCheck, Info, Trash2, X } from 'lucide-react'
import {
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
} from '@/components/primitives'
import { useNotificationsStore, type AutonomousNotification } from '@/stores'
import { cn, formatAge } from '@/lib/utils'

interface NotificationDrawerProps {
  open: boolean
  onOpenChange: (v: boolean) => void
}

/**
 * Slide-in notification drawer anchored to the right. Uses the existing
 * Dialog primitive (Radix) so focus trap, Esc-close and ARIA semantics
 * come for free; the custom class positions it as a side sheet instead
 * of a centred modal.
 */
export function NotificationDrawer({ open, onOpenChange }: NotificationDrawerProps) {
  const navigate = useNavigate()
  const items = useNotificationsStore((s) => s.items)
  const unreadCount = useNotificationsStore((s) => s.unreadCount)
  const markAsRead = useNotificationsStore((s) => s.markAsRead)
  const markAllRead = useNotificationsStore((s) => s.markAllRead)
  const clear = useNotificationsStore((s) => s.clear)
  const clearAll = useNotificationsStore((s) => s.clearAll)

  const grouped = useMemo(() => bucketByDay(items), [items])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        size="full"
        className={cn(
          'fixed inset-y-0 right-0 top-0 h-screen max-h-none w-[420px] max-w-[92vw]',
          'left-auto translate-x-0 translate-y-0',
          'rounded-none border-l border-[var(--border-default)] bg-[var(--bg-0)]',
          'p-0 flex flex-col',
          // Radix close button — hide, we render our own in the header.
          '[&>button[aria-label="Close"]]:hidden',
          'data-[state=open]:animate-in data-[state=closed]:animate-out',
          'data-[state=open]:slide-in-from-right data-[state=closed]:slide-out-to-right',
        )}
      >
        <header className="flex items-center justify-between px-3 py-2 border-b border-[var(--border-subtle)] shrink-0">
          <div className="flex items-center gap-2">
            <Bell className="h-3.5 w-3.5 text-[var(--text-2)]" />
            <DialogTitle className="text-[13px] font-semibold text-[var(--text-0)]">
              Notifications
            </DialogTitle>
            {unreadCount > 0 && (
              <span className="mono tabular-nums text-[10px] px-1.5 py-0.5 rounded-[2px] bg-[color-mix(in_oklab,var(--accent-primary)_18%,transparent)] text-[var(--accent-primary)]">
                {unreadCount} unread
              </span>
            )}
          </div>
          <div className="flex items-center gap-1">
            {unreadCount > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={markAllRead}
                aria-label="Mark all as read"
              >
                <CheckCheck className="h-3 w-3 mr-1" /> Mark all read
              </Button>
            )}
            {items.length > 0 && (
              <Button
                size="sm"
                variant="ghost"
                onClick={clearAll}
                aria-label="Clear all notifications"
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            )}
            <Button
              size="icon-sm"
              variant="ghost"
              onClick={() => onOpenChange(false)}
              aria-label="Close"
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        </header>

        <div className="flex-1 min-h-0 overflow-auto">
          {items.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full px-6 text-center">
              <Bell className="h-6 w-6 text-[var(--text-3)] mb-2" />
              <p className="text-[12px] text-[var(--text-2)]">No notifications yet.</p>
              <p className="text-[10px] text-[var(--text-3)] mt-1">
                Cycle completions, strategy retirements and system alerts appear here.
              </p>
            </div>
          ) : (
            grouped.map(({ label, rows }) => (
              <section key={label} className="py-1">
                <div className="px-3 py-1 text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                  {label}
                </div>
                <ul>
                  {rows.map((n) => (
                    <NotificationItem
                      key={n.id}
                      n={n}
                      onMarkRead={() => markAsRead(n.id)}
                      onClear={() => clear(n.id)}
                      onAction={() => {
                        if (n.actionButton?.url) {
                          if (n.actionButton.url.startsWith('/')) {
                            onOpenChange(false)
                            navigate(n.actionButton.url)
                          } else {
                            window.open(n.actionButton.url, '_blank', 'noopener')
                          }
                        }
                      }}
                    />
                  ))}
                </ul>
              </section>
            ))
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

function NotificationItem({
  n,
  onMarkRead,
  onClear,
  onAction,
}: {
  n: AutonomousNotification
  onMarkRead: () => void
  onClear: () => void
  onAction: () => void
}) {
  const Icon =
    n.severity === 'error'
      ? CircleAlert
      : n.severity === 'warning'
        ? CircleAlert
        : n.severity === 'success'
          ? CircleCheck
          : Info
  const tone =
    n.severity === 'error'
      ? 'var(--pnl-down)'
      : n.severity === 'warning'
        ? 'var(--status-warning)'
        : n.severity === 'success'
          ? 'var(--pnl-up)'
          : 'var(--accent-primary)'

  return (
    <li
      className={cn(
        'group flex items-start gap-2 px-3 py-2 border-b border-[var(--border-subtle)]',
        !n.read && 'bg-[color-mix(in_oklab,var(--accent-primary)_4%,transparent)]',
      )}
    >
      <Icon className="h-3.5 w-3.5 shrink-0 mt-0.5" style={{ color: tone }} />
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-[12px] font-medium text-[var(--text-0)] truncate">
            {n.title}
          </span>
          <span className="mono tabular-nums text-[9px] text-[var(--text-3)] shrink-0">
            {formatAge(n.timestamp)}
          </span>
        </div>
        {n.message && (
          <p className="text-[11px] text-[var(--text-2)] mt-0.5 leading-[15px]">
            {n.message}
          </p>
        )}
        <div className="flex items-center gap-1 mt-1.5">
          {n.actionButton?.url && (
            <Button size="sm" variant="secondary" onClick={onAction}>
              {n.actionButton.label}
            </Button>
          )}
          {!n.read && (
            <Button size="sm" variant="ghost" onClick={onMarkRead}>
              Mark read
            </Button>
          )}
          <Button
            size="sm"
            variant="ghost"
            onClick={onClear}
            aria-label="Clear notification"
            className="ml-auto opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
          >
            <X className="h-3 w-3" />
          </Button>
        </div>
      </div>
    </li>
  )
}

function bucketByDay(
  items: AutonomousNotification[],
): Array<{ label: string; rows: AutonomousNotification[] }> {
  const buckets = new Map<string, AutonomousNotification[]>()
  const now = new Date()
  const today = toDayKey(now)
  const yesterday = toDayKey(new Date(now.getTime() - 86_400_000))
  for (const n of items) {
    const d = new Date(n.timestamp)
    const key = Number.isNaN(d.getTime()) ? 'Earlier' : toDayKey(d)
    const list = buckets.get(key) ?? []
    list.push(n)
    buckets.set(key, list)
  }
  const ordered: Array<{ label: string; rows: AutonomousNotification[] }> = []
  for (const [key, rows] of buckets.entries()) {
    let label = key
    if (key === today) label = 'Today'
    else if (key === yesterday) label = 'Yesterday'
    else if (key !== 'Earlier') {
      const d = new Date(key)
      label = Number.isNaN(d.getTime())
        ? key
        : d.toLocaleDateString('en-GB', { month: 'short', day: 'numeric' })
    }
    ordered.push({ label, rows })
  }
  const weight = (l: string) => (l === 'Today' ? 0 : l === 'Yesterday' ? 1 : 2)
  ordered.sort((a, b) => {
    const w = weight(a.label) - weight(b.label)
    if (w !== 0) return w
    return b.rows[0]?.timestamp.localeCompare(a.rows[0]?.timestamp ?? '') || 0
  })
  return ordered
}

function toDayKey(d: Date): string {
  return d.toISOString().slice(0, 10)
}
