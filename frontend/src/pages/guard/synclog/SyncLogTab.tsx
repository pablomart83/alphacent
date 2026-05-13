import { useEffect, useRef, useState } from 'react'
import { cn } from '@/lib/utils'
import { useServiceLog, type ServiceLogEntry, type ServiceLogLevel } from '../useGuardData'

/* ─────────────────────────────────────────────────────────────────────────────
 * SyncLogTab — live terminal-style log of all backend service events.
 *
 * Services captured:
 *   price_sync · quick_update · signal_gen · autonomous_cycle
 *   tsl · order_monitor · daily_sync · news_sentiment
 *
 * Polls GET /data/service-log every 5 s. New entries flash briefly.
 * Auto-scrolls to bottom unless the user has scrolled up.
 * ─────────────────────────────────────────────────────────────────────────── */

// ── Service metadata ──────────────────────────────────────────────────────────

interface ServiceMeta {
  label: string
  color: string        // CSS color token or hex
  bg: string           // badge background (color-mix)
}

const SERVICE_META: Record<string, ServiceMeta> = {
  price_sync:       { label: 'PRICE SYNC',    color: '#60a5fa', bg: 'rgba(96,165,250,0.12)' },
  quick_update:     { label: 'QUICK UPD',     color: '#a78bfa', bg: 'rgba(167,139,250,0.12)' },
  signal_gen:       { label: 'SIGNAL GEN',    color: '#34d399', bg: 'rgba(52,211,153,0.12)' },
  autonomous_cycle: { label: 'AUTO CYCLE',    color: '#f59e0b', bg: 'rgba(245,158,11,0.12)' },
  tsl:              { label: 'TSL',           color: '#fb923c', bg: 'rgba(251,146,60,0.12)' },
  order_monitor:    { label: 'ORDER MON',     color: '#e879f9', bg: 'rgba(232,121,249,0.12)' },
  daily_sync:       { label: 'DAILY SYNC',    color: '#94a3b8', bg: 'rgba(148,163,184,0.12)' },
  news_sentiment:   { label: 'NEWS SENT',     color: '#2dd4bf', bg: 'rgba(45,212,191,0.12)' },
}

const FALLBACK_META: ServiceMeta = {
  label: 'SYSTEM',
  color: '#94a3b8',
  bg: 'rgba(148,163,184,0.12)',
}

function getServiceMeta(service: string): ServiceMeta {
  return SERVICE_META[service] ?? FALLBACK_META
}

// ── Level styling ─────────────────────────────────────────────────────────────

const LEVEL_COLOR: Record<ServiceLogLevel, string> = {
  info:    'var(--text-2)',
  success: 'var(--pnl-up)',
  warning: 'var(--status-warning)',
  error:   'var(--pnl-down)',
}

const LEVEL_ICON: Record<ServiceLogLevel, string> = {
  info:    '·',
  success: '✓',
  warning: '⚠',
  error:   '✗',
}

// ── Filter bar ────────────────────────────────────────────────────────────────

const ALL_SERVICES = Object.keys(SERVICE_META)

interface FilterState {
  services: Set<string>
  levels: Set<ServiceLogLevel>
  search: string
}

// ── Row component ─────────────────────────────────────────────────────────────

function LogRow({ entry, isNew }: { entry: ServiceLogEntry; isNew: boolean }) {
  const meta = getServiceMeta(entry.service)
  const levelColor = LEVEL_COLOR[entry.level] ?? LEVEL_COLOR.info
  const icon = LEVEL_ICON[entry.level] ?? '·'

  return (
    <div
      className={cn(
        'flex items-start gap-2 px-2 py-[3px] rounded-[2px] transition-colors duration-700',
        isNew && 'bg-[rgba(255,255,255,0.04)]',
      )}
    >
      {/* Timestamp */}
      <span className="shrink-0 mono text-[9px] tabular-nums text-[var(--text-3)] pt-[1px] w-[52px]">
        {entry.ts}
      </span>

      {/* Service badge */}
      <span
        className="shrink-0 mono text-[8px] font-bold uppercase tracking-wider px-1 py-[1px] rounded-[2px] w-[72px] text-center"
        style={{ color: meta.color, backgroundColor: meta.bg }}
      >
        {meta.label}
      </span>

      {/* Level icon */}
      <span
        className="shrink-0 mono text-[10px] font-bold w-[10px] text-center"
        style={{ color: levelColor }}
      >
        {icon}
      </span>

      {/* Event + detail */}
      <span className="flex-1 min-w-0 mono text-[10px] leading-snug break-words">
        <span style={{ color: levelColor }}>{entry.event}</span>
        {entry.detail && (
          <span className="ml-2 text-[var(--text-3)] text-[9px]">{entry.detail}</span>
        )}
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

export function SyncLogTab() {
  const { data, isLoading } = useServiceLog(true)
  const scrollRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const [newSeqs, setNewSeqs] = useState<Set<number>>(new Set())
  const prevSeqRef = useRef<number>(0)

  // Filter state
  const [filter, setFilter] = useState<FilterState>({
    services: new Set(ALL_SERVICES),
    levels: new Set<ServiceLogLevel>(['info', 'success', 'warning', 'error']),
    search: '',
  })

  // Track new entries and flash them
  useEffect(() => {
    if (!data?.entries.length) return
    const latest = data.entries[data.entries.length - 1].seq
    if (latest <= prevSeqRef.current) return

    const fresh = new Set(
      data.entries.filter((e) => e.seq > prevSeqRef.current).map((e) => e.seq),
    )
    prevSeqRef.current = latest
    setNewSeqs(fresh)
    const t = setTimeout(() => setNewSeqs(new Set()), 1200)
    return () => clearTimeout(t)
  }, [data])

  // Auto-scroll to bottom
  useEffect(() => {
    if (!autoScroll || !scrollRef.current) return
    scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [data, autoScroll])

  // Detect manual scroll-up
  const handleScroll = () => {
    const el = scrollRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40
    setAutoScroll(atBottom)
  }

  // Filtered entries
  const entries = (data?.entries ?? []).filter((e) => {
    if (!filter.services.has(e.service)) return false
    if (!filter.levels.has(e.level)) return false
    if (filter.search) {
      const q = filter.search.toLowerCase()
      if (!e.event.toLowerCase().includes(q) && !(e.detail ?? '').toLowerCase().includes(q)) return false
    }
    return true
  })

  const toggleService = (svc: string) => {
    setFilter((f) => {
      const next = new Set(f.services)
      next.has(svc) ? next.delete(svc) : next.add(svc)
      return { ...f, services: next }
    })
  }

  const toggleLevel = (lvl: ServiceLogLevel) => {
    setFilter((f) => {
      const next = new Set(f.levels)
      next.has(lvl) ? next.delete(lvl) : next.add(lvl)
      return { ...f, levels: next }
    })
  }

  return (
    <div className="flex flex-col h-full min-h-0 bg-[var(--bg-0)]">

      {/* ── Filter bar ── */}
      <div className="shrink-0 px-3 pt-2 pb-1.5 border-b border-[var(--border-subtle)] space-y-1.5">

        {/* Service toggles */}
        <div className="flex flex-wrap gap-1">
          {ALL_SERVICES.map((svc) => {
            const meta = getServiceMeta(svc)
            const active = filter.services.has(svc)
            return (
              <button
                key={svc}
                onClick={() => toggleService(svc)}
                className={cn(
                  'mono text-[8px] font-bold uppercase tracking-wider px-1.5 py-[2px] rounded-[2px]',
                  'transition-opacity duration-150 cursor-pointer',
                  !active && 'opacity-30',
                )}
                style={{ color: meta.color, backgroundColor: meta.bg }}
              >
                {meta.label}
              </button>
            )
          })}
        </div>

        {/* Level toggles + search */}
        <div className="flex items-center gap-2">
          {(['info', 'success', 'warning', 'error'] as ServiceLogLevel[]).map((lvl) => {
            const active = filter.levels.has(lvl)
            return (
              <button
                key={lvl}
                onClick={() => toggleLevel(lvl)}
                className={cn(
                  'mono text-[8px] uppercase tracking-wider px-1.5 py-[2px] rounded-[2px]',
                  'border transition-opacity duration-150 cursor-pointer',
                  !active && 'opacity-30',
                )}
                style={{
                  color: LEVEL_COLOR[lvl],
                  borderColor: `color-mix(in oklab, ${LEVEL_COLOR[lvl]} 40%, transparent)`,
                  backgroundColor: `color-mix(in oklab, ${LEVEL_COLOR[lvl]} 8%, transparent)`,
                }}
              >
                {LEVEL_ICON[lvl]} {lvl}
              </button>
            )
          })}

          <input
            type="text"
            placeholder="filter…"
            value={filter.search}
            onChange={(e) => setFilter((f) => ({ ...f, search: e.target.value }))}
            className={cn(
              'ml-auto mono text-[10px] bg-[var(--bg-1)] border border-[var(--border-subtle)]',
              'rounded-[2px] px-2 py-[2px] text-[var(--text-1)] placeholder:text-[var(--text-3)]',
              'outline-none focus:border-[var(--accent-primary)] w-[120px]',
            )}
          />

          {/* Auto-scroll indicator */}
          <button
            onClick={() => {
              setAutoScroll(true)
              if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
            }}
            className={cn(
              'mono text-[8px] uppercase tracking-wider px-1.5 py-[2px] rounded-[2px]',
              'border transition-colors duration-150 cursor-pointer',
              autoScroll
                ? 'text-[var(--pnl-up)] border-[color-mix(in_oklab,var(--pnl-up)_40%,transparent)] bg-[color-mix(in_oklab,var(--pnl-up)_8%,transparent)]'
                : 'text-[var(--text-3)] border-[var(--border-subtle)] bg-transparent',
            )}
            title={autoScroll ? 'Auto-scroll on' : 'Click to resume auto-scroll'}
          >
            ↓ live
          </button>
        </div>
      </div>

      {/* ── Log body ── */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 min-h-0 overflow-auto px-1 py-1"
      >
        {isLoading && entries.length === 0 && (
          <div className="flex items-center justify-center h-full text-[var(--text-3)] mono text-[10px]">
            Loading service log…
          </div>
        )}

        {!isLoading && entries.length === 0 && (
          <div className="flex flex-col items-center justify-center h-full gap-2 text-[var(--text-3)]">
            <span className="mono text-[10px]">No events yet.</span>
            <span className="mono text-[9px] opacity-60">
              Events appear as the backend runs price syncs, signal generation, TSL cycles, etc.
            </span>
          </div>
        )}

        {entries.map((entry) => (
          <LogRow key={entry.seq} entry={entry} isNew={newSeqs.has(entry.seq)} />
        ))}
      </div>

      {/* ── Footer stats ── */}
      <div className="shrink-0 px-3 py-1 border-t border-[var(--border-subtle)] flex items-center gap-3">
        <span className="mono text-[9px] text-[var(--text-3)]">
          {entries.length} events shown
          {data?.total != null && data.total !== entries.length && ` (${data.total} total)`}
        </span>
        <span className="mono text-[9px] text-[var(--text-3)] ml-auto">
          polling every 5s
        </span>
      </div>
    </div>
  )
}
