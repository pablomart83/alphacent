import { NavLink, useNavigate } from 'react-router-dom'
import { Bell, Command, HelpCircle, LogOut, Settings as SettingsIcon } from 'lucide-react'
import { Button } from '@/components/primitives'
import { AccountToggle } from './AccountToggle'
import { WebSocketIndicator } from './WebSocketIndicator'
import { useCommandPalette, useNotificationsStore, useUiOverlays } from '@/stores'
import { useLogout } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'

const NAV_ITEMS = [
  { path: '/', label: 'Command', shortcut: 'G C' },
  { path: '/book', label: 'Book', shortcut: 'G B' },
  { path: '/strategies', label: 'Strategies', shortcut: 'G S' },
  { path: '/guard', label: 'Guard', shortcut: 'G G' },
  { path: '/research', label: 'Research', shortcut: 'G R' },
  { path: '/intel', label: 'Intel', shortcut: 'G I' },
] as const

interface TopNavBarProps {
  liveEnabled?: boolean
}

export function TopNavBar({ liveEnabled = false }: TopNavBarProps) {
  const navigate = useNavigate()
  const openPalette = useCommandPalette((s) => s.setOpen)
  const setNotificationsOpen = useUiOverlays((s) => s.setNotificationsOpen)
  const setShortcutHelpOpen = useUiOverlays((s) => s.setShortcutHelpOpen)
  const unreadCount = useNotificationsStore((s) => s.unreadCount)
  const logout = useLogout()
  const handleLogout = async () => {
    await logout.mutateAsync()
    navigate('/login', { replace: true })
  }

  const isMac = typeof navigator !== 'undefined' && /Mac|iP(hone|od|ad)/.test(navigator.platform)

  return (
    <header
      className="flex items-center justify-between px-3 shrink-0 bg-[var(--bg-0)] border-b border-[var(--border-subtle)]"
      style={{ height: 'var(--shell-topnav-h)' }}
    >
      <div className="flex items-center gap-4 min-w-0">
        <NavLink
          to="/"
          className="flex items-center gap-2 shrink-0 group"
          aria-label="AlphaCent home"
        >
          <svg width={18} height={18} viewBox="0 0 32 32" aria-hidden>
            <rect width="32" height="32" rx="4" fill="var(--bg-2)" />
            <path
              d="M7 23 L13 9 L19 23 M9.5 18 L16.5 18"
              stroke="var(--pnl-up)"
              strokeWidth={2.2}
              fill="none"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
            <circle cx={24} cy={23} r={2} fill="var(--pnl-up)" />
          </svg>
          <span className="text-[12px] font-semibold tracking-tight text-[var(--text-0)] group-hover:text-[var(--accent-primary)] transition-colors">
            AlphaCent
          </span>
        </NavLink>

        <nav className="flex items-center gap-0.5" aria-label="Primary">
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              className={({ isActive }) =>
                cn(
                  'relative px-2.5 h-7 inline-flex items-center rounded-[2px]',
                  'text-[11px] font-medium transition-colors',
                  'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]',
                  isActive
                    ? 'text-[var(--text-0)] bg-[var(--bg-active)]'
                    : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
                )
              }
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </div>

      <div className="flex items-center gap-2">
        <WebSocketIndicator />

        <Button
          variant="ghost"
          size="sm"
          onClick={() => openPalette(true)}
          className="gap-1.5 text-[var(--text-2)]"
          aria-label="Open command palette"
        >
          <Command className="h-3 w-3" />
          <span className="mono text-[10px]">{isMac ? '⌘K' : 'Ctrl+K'}</span>
        </Button>

        <button
          type="button"
          onClick={() => setNotificationsOpen(true)}
          aria-label={
            unreadCount > 0
              ? `Notifications — ${unreadCount} unread`
              : 'Notifications'
          }
          className={cn(
            'relative inline-flex items-center justify-center h-7 w-7 rounded-[2px] transition-colors',
            'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
            'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]',
          )}
        >
          <Bell className="h-3.5 w-3.5" />
          {unreadCount > 0 && (
            <span
              className="absolute -top-0.5 -right-0.5 h-3.5 min-w-[14px] px-1 rounded-full bg-[var(--pnl-down)] text-[9px] font-semibold mono tabular-nums text-white flex items-center justify-center"
              aria-hidden
            >
              {unreadCount > 99 ? '99+' : unreadCount}
            </span>
          )}
        </button>

        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => setShortcutHelpOpen(true)}
          aria-label="Keyboard shortcut help"
        >
          <HelpCircle className="h-3.5 w-3.5" />
        </Button>

        <AccountToggle liveEnabled={liveEnabled} />

        <Button
          variant="ghost"
          size="icon-sm"
          onClick={() => navigate('/settings')}
          aria-label="Settings"
        >
          <SettingsIcon className="h-3.5 w-3.5" />
        </Button>

        <Button
          variant="ghost"
          size="icon-sm"
          onClick={handleLogout}
          aria-label="Log out"
        >
          <LogOut className="h-3.5 w-3.5" />
        </Button>
      </div>
    </header>
  )
}
