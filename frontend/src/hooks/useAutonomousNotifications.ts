import { useEffect } from 'react'
import { wsManager } from '@/services/websocket'
import { useNotificationsStore, type AutonomousNotification } from '@/stores'

/**
 * Subscribe to the `autonomous_notifications` WS channel and push each
 * arriving notification into the notifications store. Mounted once in
 * AppShell — the drawer and any toast reads the same store, so there's
 * one source of truth.
 *
 * Backend payload shape per `websocket_manager.py` broadcasts:
 *   { id, type, severity, title, message, timestamp, data, actionButton? }
 *
 * Anything missing is defaulted so a malformed message never crashes
 * the store.
 */
export function useAutonomousNotifications() {
  const add = useNotificationsStore((s) => s.add)

  useEffect(() => {
    const unsubs: Array<() => void> = []

    // Primary channel — authored notifications from the autonomous cycle.
    unsubs.push(
      wsManager.on('autonomous_notifications', (raw) => {
        const n = toNotification(raw)
        if (n) add(n)
      }),
    )

    // Cycle lifecycle — synthesise a notification so the drawer always
    // reflects a completed run even if the dedicated channel fires late.
    unsubs.push(
      wsManager.on('autonomous_cycle', (raw) => {
        const n = cycleToNotification(raw)
        if (n) add(n)
      }),
    )

    return () => {
      unsubs.forEach((u) => u())
    }
  }, [add])
}

function toNotification(raw: unknown): AutonomousNotification | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = String(r.id ?? `notif-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`)
  const type = String(r.type ?? 'autonomous_event')
  const severity = normaliseSeverity(r.severity)
  const title = String(r.title ?? type.replace(/_/g, ' '))
  const message = String(r.message ?? '')
  const timestamp = String(r.timestamp ?? new Date().toISOString())
  const action = r.actionButton
  return {
    id,
    type,
    severity,
    title,
    message,
    timestamp,
    read: false,
    data: r.data,
    actionButton:
      action && typeof action === 'object'
        ? {
            label: String((action as Record<string, unknown>).label ?? 'Open'),
            action: String((action as Record<string, unknown>).action ?? ''),
            url:
              typeof (action as Record<string, unknown>).url === 'string'
                ? String((action as Record<string, unknown>).url)
                : undefined,
          }
        : undefined,
  }
}

function cycleToNotification(raw: unknown): AutonomousNotification | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const phase = String(r.phase ?? r.status ?? r.event ?? '')
  if (!phase || !['completed', 'failed', 'started'].includes(phase)) return null
  const cycleId = String(r.cycle_id ?? r.id ?? '')
  const id = `cycle-${phase}-${cycleId || Date.now()}`
  const severity: AutonomousNotification['severity'] =
    phase === 'failed' ? 'error' : phase === 'completed' ? 'success' : 'info'
  const title =
    phase === 'completed'
      ? 'Cycle completed'
      : phase === 'failed'
        ? 'Cycle failed'
        : 'Cycle started'
  const stats =
    phase === 'completed'
      ? [
          activity(r, 'proposals_generated', 'proposed'),
          activity(r, 'activated', 'activated'),
          activity(r, 'strategies_retired', 'retired'),
        ]
          .filter(Boolean)
          .join(' · ')
      : ''
  const message = stats || String(r.message ?? '')
  return {
    id,
    type: `cycle_${phase}`,
    severity,
    title,
    message,
    timestamp: String(r.completed_at ?? r.timestamp ?? new Date().toISOString()),
    read: false,
    data: r,
  }
}

function normaliseSeverity(v: unknown): AutonomousNotification['severity'] {
  const s = String(v ?? '').toLowerCase()
  if (s === 'success' || s === 'warning' || s === 'error' || s === 'info') {
    return s as AutonomousNotification['severity']
  }
  if (s === 'critical') return 'error'
  return 'info'
}

function activity(r: Record<string, unknown>, key: string, label: string): string | null {
  const v = r[key]
  if (typeof v !== 'number' || v === 0) return null
  return `${v} ${label}`
}
