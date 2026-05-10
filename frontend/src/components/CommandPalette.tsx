import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import Fuse from 'fuse.js'
import { useCommandPalette } from '@/stores'
import {
  ChevronRight,
  Command as CommandIcon,
  Compass,
  Database,
  LineChart,
  Shield,
  Rocket,
  ListTree,
  Settings as SettingsIcon,
  Moon,
  Sun,
  LogOut,
  History,
  TerminalSquare,
  Briefcase,
} from 'lucide-react'
import { useTheme } from '@/stores'
import { Dialog, DialogContent, DialogTitle } from '@/components/primitives'

/**
 * ⌘K command palette.
 *
 * Items are fuse-searched across label + keywords. Recent commands
 * persist in the existing command-palette Zustand store.
 */

type CommandItem = {
  id: string
  label: string
  keywords?: string
  section: 'Navigate' | 'Surfaces' | 'Actions' | 'Settings'
  icon: React.ComponentType<{ className?: string }>
  run: (ctx: RunContext) => void
}

interface RunContext {
  navigate: ReturnType<typeof useNavigate>
  close: () => void
  setTheme: (t: 'light' | 'dark') => void
}

const COMMANDS: CommandItem[] = [
  {
    id: 'nav-command',
    label: 'Go to Command',
    keywords: 'pulse equity stream home dashboard',
    section: 'Navigate',
    icon: Compass,
    run: ({ navigate, close }) => {
      navigate('/')
      close()
    },
  },
  {
    id: 'nav-book',
    label: 'Go to Book',
    keywords: 'positions orders execution live',
    section: 'Navigate',
    icon: Briefcase,
    run: ({ navigate, close }) => {
      navigate('/book')
      close()
    },
  },
  {
    id: 'nav-strategies',
    label: 'Go to Strategies',
    keywords: 'library cycle templates symbols graduation lab',
    section: 'Navigate',
    icon: ListTree,
    run: ({ navigate, close }) => {
      navigate('/strategies')
      close()
    },
  },
  {
    id: 'nav-guard',
    label: 'Go to Guard',
    keywords: 'risk gates system breakers alerts audit',
    section: 'Navigate',
    icon: Shield,
    run: ({ navigate, close }) => {
      navigate('/guard')
      close()
    },
  },
  {
    id: 'nav-research',
    label: 'Go to Research',
    keywords: 'performance attribution trades regime alpha tear sheet stress journal',
    section: 'Navigate',
    icon: LineChart,
    run: ({ navigate, close }) => {
      navigate('/research')
      close()
    },
  },
  {
    id: 'nav-settings',
    label: 'Go to Settings',
    keywords: 'configuration preferences',
    section: 'Navigate',
    icon: SettingsIcon,
    run: ({ navigate, close }) => {
      navigate('/settings')
      close()
    },
  },
  // Surfaces — sub-routes
  {
    id: 'surface-book-positions',
    label: 'Book / Positions',
    section: 'Surfaces',
    icon: Briefcase,
    run: ({ navigate, close }) => {
      navigate('/book/positions')
      close()
    },
  },
  {
    id: 'surface-book-orders',
    label: 'Book / Orders',
    section: 'Surfaces',
    icon: Briefcase,
    run: ({ navigate, close }) => {
      navigate('/book/orders')
      close()
    },
  },
  {
    id: 'surface-book-live',
    label: 'Book / Live',
    section: 'Surfaces',
    icon: Rocket,
    run: ({ navigate, close }) => {
      navigate('/book/live')
      close()
    },
  },
  {
    id: 'surface-strategies-cycle',
    label: 'Strategies / Cycle',
    section: 'Surfaces',
    icon: History,
    run: ({ navigate, close }) => {
      navigate('/strategies/cycle')
      close()
    },
  },
  {
    id: 'surface-strategies-graduation',
    label: 'Strategies / Graduation',
    section: 'Surfaces',
    icon: Rocket,
    run: ({ navigate, close }) => {
      navigate('/strategies/graduation')
      close()
    },
  },
  {
    id: 'surface-guard-risk',
    label: 'Guard / Risk',
    section: 'Surfaces',
    icon: Shield,
    run: ({ navigate, close }) => {
      navigate('/guard/risk')
      close()
    },
  },
  {
    id: 'surface-guard-system',
    label: 'Guard / System',
    section: 'Surfaces',
    icon: Database,
    run: ({ navigate, close }) => {
      navigate('/guard/system')
      close()
    },
  },
  {
    id: 'surface-guard-audit',
    label: 'Guard / Audit',
    section: 'Surfaces',
    icon: TerminalSquare,
    run: ({ navigate, close }) => {
      navigate('/guard/audit')
      close()
    },
  },
  {
    id: 'surface-research-performance',
    label: 'Research / Performance',
    section: 'Surfaces',
    icon: LineChart,
    run: ({ navigate, close }) => {
      navigate('/research/performance')
      close()
    },
  },
  {
    id: 'surface-research-journal',
    label: 'Research / Journal',
    section: 'Surfaces',
    icon: TerminalSquare,
    run: ({ navigate, close }) => {
      navigate('/research/journal')
      close()
    },
  },
  // Theme / logout
  {
    id: 'theme-dark',
    label: 'Switch to dark theme',
    keywords: 'theme appearance night',
    section: 'Settings',
    icon: Moon,
    run: ({ setTheme, close }) => {
      setTheme('dark')
      close()
    },
  },
  {
    id: 'theme-light',
    label: 'Switch to light theme',
    keywords: 'theme appearance day',
    section: 'Settings',
    icon: Sun,
    run: ({ setTheme, close }) => {
      setTheme('light')
      close()
    },
  },
  {
    id: 'action-logout',
    label: 'Sign out',
    keywords: 'logout exit',
    section: 'Actions',
    icon: LogOut,
    run: async ({ close }) => {
      close()
      try {
        await fetch(`${import.meta.env.VITE_API_BASE_URL || ''}/auth/logout`, {
          method: 'POST',
          credentials: 'include',
        })
      } catch {
        /* swallow — always land on login */
      }
      window.location.href = '/login'
    },
  },
]

export function CommandPalette() {
  const navigate = useNavigate()
  const open = useCommandPalette((s) => s.open)
  const setOpen = useCommandPalette((s) => s.setOpen)
  const recent = useCommandPalette((s) => s.recentCommands)
  const pushRecent = useCommandPalette((s) => s.pushRecent)
  const setTheme = useTheme((s) => s.setTheme)
  const [query, setQuery] = useState('')
  const [activeIdx, setActiveIdx] = useState(0)
  const inputRef = useRef<HTMLInputElement>(null)

  const fuse = useMemo(
    () =>
      new Fuse(COMMANDS, {
        keys: ['label', 'keywords', 'section'],
        threshold: 0.4,
      }),
    [],
  )

  const grouped = useMemo(() => {
    const items = query.trim()
      ? fuse.search(query).map((r) => r.item)
      : orderByRecent(COMMANDS, recent)
    const groups: Record<string, CommandItem[]> = {}
    for (const it of items) {
      const key = query.trim() ? it.section : isRecent(it.id, recent) ? 'Recent' : it.section
      groups[key] = groups[key] ?? []
      groups[key].push(it)
    }
    return groups
  }, [fuse, query, recent])

  const flat = useMemo(() => {
    const out: CommandItem[] = []
    for (const k of Object.keys(grouped)) {
      out.push(...grouped[k])
    }
    return out
  }, [grouped])

  useEffect(() => {
    setActiveIdx(0)
  }, [query, open])

  useEffect(() => {
    if (open) {
      setQuery('')
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const run = (item: CommandItem) => {
    item.run({ navigate, close: () => setOpen(false), setTheme })
    pushRecent(item.id)
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogContent size="lg" className="p-0 overflow-hidden">
        <DialogTitle className="sr-only">Command palette</DialogTitle>
        <div className="flex items-center gap-2 border-b border-[var(--border-subtle)] px-3 py-2">
          <CommandIcon className="h-3.5 w-3.5 text-[var(--text-3)]" />
          <input
            ref={inputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'ArrowDown') {
                e.preventDefault()
                setActiveIdx((i) => Math.min(flat.length - 1, i + 1))
              } else if (e.key === 'ArrowUp') {
                e.preventDefault()
                setActiveIdx((i) => Math.max(0, i - 1))
              } else if (e.key === 'Enter') {
                e.preventDefault()
                const item = flat[activeIdx]
                if (item) run(item)
              }
            }}
            placeholder="Type a command or jump to a surface…"
            className="flex-1 bg-transparent outline-none text-[13px] text-[var(--text-0)] placeholder:text-[var(--text-3)]"
          />
          <kbd className="mono text-[9px] px-1.5 py-0.5 bg-[var(--bg-2)] border border-[var(--border-subtle)] rounded-[2px] text-[var(--text-3)]">
            Esc
          </kbd>
        </div>
        <div className="max-h-[360px] overflow-auto py-1">
          {Object.keys(grouped).map((section) => (
            <div key={section}>
              <div className="px-3 pt-2 pb-1 text-[9px] uppercase tracking-wider text-[var(--text-3)]">
                {section}
              </div>
              {grouped[section].map((item) => {
                const globalIdx = flat.indexOf(item)
                const active = globalIdx === activeIdx
                return (
                  <button
                    key={item.id}
                    onClick={() => run(item)}
                    onMouseMove={() => setActiveIdx(globalIdx)}
                    className={
                      'flex items-center gap-2.5 w-full text-left px-3 py-1.5 transition-colors ' +
                      (active
                        ? 'bg-[color-mix(in_oklab,var(--accent-primary)_12%,transparent)] text-[var(--text-0)]'
                        : 'text-[var(--text-1)] hover:bg-[var(--bg-hover)]')
                    }
                  >
                    <item.icon className="h-3.5 w-3.5 text-[var(--text-3)]" />
                    <span className="text-[12px] flex-1 truncate">{item.label}</span>
                    {active && (
                      <ChevronRight className="h-3 w-3 text-[var(--accent-primary)]" />
                    )}
                  </button>
                )
              })}
            </div>
          ))}
          {flat.length === 0 && (
            <div className="px-4 py-6 text-center text-[12px] text-[var(--text-3)]">
              No matches. Try another query.
            </div>
          )}
        </div>
        <div className="flex items-center justify-between border-t border-[var(--border-subtle)] px-3 py-1.5 text-[9px] text-[var(--text-3)]">
          <div className="flex items-center gap-2">
            <span>
              <kbd className="mono">↑</kbd> / <kbd className="mono">↓</kbd> navigate
            </span>
            <span>
              <kbd className="mono">↵</kbd> select
            </span>
          </div>
          <span>{flat.length} result{flat.length === 1 ? '' : 's'}</span>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function isRecent(id: string, recent: string[]): boolean {
  return recent.includes(id)
}

function orderByRecent(items: CommandItem[], recent: string[]): CommandItem[] {
  if (!recent.length) return items
  const recentSet = new Set(recent)
  const recentItems = recent
    .map((id) => items.find((i) => i.id === id))
    .filter((v): v is CommandItem => v != null)
  const rest = items.filter((i) => !recentSet.has(i.id))
  return [...recentItems, ...rest]
}
