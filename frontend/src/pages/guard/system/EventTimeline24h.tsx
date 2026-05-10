import { useMemo } from 'react'
import { SectionLabel } from '@/components/layout'
import { EmptyState } from '@/components/primitives'
import { Clock } from 'lucide-react'
import { formatTimestamp, parseUtcIso } from '@/lib/utils'
import type { SystemHealthPayload } from '../useGuardData'

interface RawEvent {
  timestamp: string
  type: string
  description: string
  severity?: string
}

interface EventTimeline24hProps {
  health: SystemHealthPayload | null | undefined
  loading?: boolean
}

/**
 * EventTimeline24h — horizontal 24h timeline of /control/system-health.events_24h.
 * Events are plotted by hour offset from "now"; hover shows full description.
 */
export function EventTimeline24h({ health, loading }: EventTimeline24hProps) {
  const events = (health?.events_24h ?? []) as unknown as RawEvent[]

  const positioned = useMemo(() => {
    const now = Date.now()
    return events
      .map((e) => {
        const ts = parseUtcIso(e.timestamp)?.getTime() ?? Date.parse(e.timestamp)
        if (!Number.isFinite(ts)) return null
        const ageMs = now - ts
        if (ageMs < 0 || ageMs > 24 * 60 * 60 * 1000) return null
        const pct = (ageMs / (24 * 60 * 60 * 1000)) * 100
        return { event: e, pctFromRight: pct }
      })
      .filter((x): x is { event: RawEvent; pctFromRight: number } => !!x)
  }, [events])

  const severityColor = (sev?: string): string => {
    switch (sev) {
      case 'error':
      case 'danger':
      case 'critical':
        return 'var(--pnl-down)'
      case 'warning':
        return 'var(--status-warning)'
      case 'info':
      default:
        return 'var(--accent-primary)'
    }
  }

  if (loading && events.length === 0) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Last 24h events</SectionLabel>
        <div className="h-[40px] rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] animate-pulse" />
      </section>
    )
  }

  if (positioned.length === 0) {
    return (
      <section className="space-y-1.5">
        <SectionLabel>Last 24h events</SectionLabel>
        <EmptyState
          icon={Clock}
          title="No events in the last 24h"
          description="Restarts, circuit trips, data gaps and errors surface here."
          className="py-6"
        />
      </section>
    )
  }

  return (
    <section className="space-y-1.5">
      <SectionLabel>Last 24h events · {positioned.length}</SectionLabel>
      <div className="rounded-[3px] border border-[var(--border-subtle)] bg-[var(--bg-1)] px-2 py-4">
        <div className="relative h-12">
          {/* Baseline */}
          <div className="absolute inset-x-0 top-1/2 h-px bg-[var(--border-subtle)]" />
          {/* Tick marks every 6h */}
          {[0, 6, 12, 18, 24].map((h) => (
            <div
              key={h}
              className="absolute top-1/2 -translate-y-1/2 h-2 w-[1px] bg-[var(--border-subtle)]"
              style={{ right: `${(h / 24) * 100}%` }}
            />
          ))}
          {/* Events */}
          {positioned.map((p, i) => {
            const color = severityColor(p.event.severity)
            return (
              <div
                key={`${p.event.timestamp}-${i}`}
                className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 h-3 w-3 rounded-full"
                style={{
                  right: `${Math.max(0, Math.min(100, p.pctFromRight))}%`,
                  backgroundColor: color,
                  boxShadow: `0 0 0 2px color-mix(in oklab, ${color} 20%, transparent)`,
                }}
                title={`${formatTimestamp(p.event.timestamp, 'long') || ''} · ${p.event.type}: ${p.event.description}`}
              />
            )
          })}
        </div>
        <div className="flex items-center justify-between mt-1 text-[9px] uppercase tracking-wider text-[var(--text-3)]">
          <span>24h ago</span>
          <span>12h</span>
          <span>now</span>
        </div>
      </div>
    </section>
  )
}
