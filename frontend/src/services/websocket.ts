/**
 * WebSocket manager — singleton.
 *
 * Design:
 * - One connection per session, shared across the app.
 * - Exponential backoff reconnection (1s → 30s, max 10 attempts in 5min).
 * - Auth failures (close code 1008 / 4001) STOP reconnection and emit
 *   a single auth-error event — no point retrying with a dead cookie.
 * - Channel+event messages (`{channel, event, data}`) are normalised to a
 *   flat `type` string so consumers subscribe by type.
 * - Connection state is observable for UI indicators.
 * - On reconnect, callers should `queryClient.invalidateQueries(...)` on
 *   the top-level keys to resync data. This file is queue-agnostic.
 */

import { notifyAuthError } from './auth-events'

const WS_BASE_URL = import.meta.env.VITE_WS_BASE_URL || ''

export type ConnectionState = 'connecting' | 'open' | 'closing' | 'closed'

export type WsMessage = {
  type: string
  data: unknown
  timestamp?: string
}

type MessageHandler = (data: any) => void
type ConnectionStateHandler = (state: ConnectionState, info: { attempt: number; lastMessageAt: number | null }) => void

const CHANNEL_MAP: Record<string, string> = {
  'autonomous:status': 'autonomous_status',
  'autonomous:cycle': 'autonomous_cycle',
  'autonomous:strategies': 'autonomous_strategies',
  'autonomous:notifications': 'autonomous_notifications',
}

const THROTTLE_MS: Record<string, number> = {
  market_data: 1000,
  autonomous_status: 2000,
  position_update: 500,
}

class WebSocketManager {
  private ws: WebSocket | null = null
  private state: ConnectionState = 'closed'
  private reconnectAttempts = 0
  private reconnectTimer: number | null = null
  private maxReconnectAttempts = 10
  private baseDelayMs = 1000
  private maxDelayMs = 30_000
  private intentionallyClosed = false
  private lastMessageAt: number | null = null

  private handlers = new Map<string, Set<MessageHandler>>()
  private stateHandlers = new Set<ConnectionStateHandler>()

  private throttleTimers = new Map<string, number>()
  private lastDispatchAt = new Map<string, number>()
  private pending = new Map<string, WsMessage>()

  connect(): void {
    if (this.ws && (this.state === 'open' || this.state === 'connecting')) return

    const sessionId = this.getCookie('session_id')
    if (!sessionId) {
      console.warn('[ws] no session_id cookie; cannot connect')
      return
    }

    this.intentionallyClosed = false
    this.setState('connecting')

    try {
      const url = `${WS_BASE_URL}/ws?session_id=${encodeURIComponent(sessionId)}`
      this.ws = new WebSocket(url)

      this.ws.onopen = () => {
        this.reconnectAttempts = 0
        this.setState('open')
      }

      this.ws.onmessage = (event) => {
        this.lastMessageAt = Date.now()
        try {
          const parsed = JSON.parse(event.data)
          const normalised = this.normalise(parsed)
          if (normalised) this.route(normalised)
        } catch (e) {
          console.warn('[ws] parse failed', e)
        }
      }

      this.ws.onerror = () => {
        // onclose will fire next
      }

      this.ws.onclose = (event) => {
        this.setState('closed')
        this.ws = null
        if (this.intentionallyClosed) return

        // Auth failures: backend closes with 1008 (Policy Violation) on
        // missing or invalid session. Don't retry with a dead cookie —
        // ping the app so it can clear state and redirect. 4001 is
        // reserved for future app-level auth codes.
        if (event.code === 1008 || event.code === 4001) {
          this.intentionallyClosed = true
          // Reset so a fresh login can reconnect cleanly.
          this.reconnectAttempts = 0
          notifyAuthError(event.code === 4001 ? 'ws-4001' : 'ws-1008')
          return
        }

        this.scheduleReconnect()
      }
    } catch (e) {
      console.error('[ws] connect failed', e)
      this.scheduleReconnect()
    }
  }

  disconnect(): void {
    this.intentionallyClosed = true
    if (this.reconnectTimer) {
      window.clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    this.throttleTimers.forEach((id) => window.clearTimeout(id))
    this.throttleTimers.clear()
    this.pending.clear()
    if (this.ws) {
      this.ws.close()
      this.ws = null
    }
    this.setState('closed')
  }

  /** Force a reconnect attempt. Resets the backoff counter. */
  forceReconnect(): void {
    if (this.ws) this.ws.close()
    this.reconnectAttempts = 0
    this.connect()
  }

  isConnected(): boolean {
    return this.state === 'open'
  }

  getState(): ConnectionState {
    return this.state
  }

  getLastMessageAt(): number | null {
    return this.lastMessageAt
  }

  getReconnectAttempts(): number {
    return this.reconnectAttempts
  }

  /** Subscribe to a message type. Returns an unsubscribe fn. */
  on(type: string, handler: MessageHandler): () => void {
    let set = this.handlers.get(type)
    if (!set) {
      set = new Set()
      this.handlers.set(type, set)
    }
    set.add(handler)
    return () => {
      const s = this.handlers.get(type)
      if (s) {
        s.delete(handler)
        if (s.size === 0) this.handlers.delete(type)
      }
    }
  }

  /** Subscribe to connection state changes. Immediately invokes with current state. */
  onStateChange(handler: ConnectionStateHandler): () => void {
    this.stateHandlers.add(handler)
    handler(this.state, { attempt: this.reconnectAttempts, lastMessageAt: this.lastMessageAt })
    return () => {
      this.stateHandlers.delete(handler)
    }
  }

  /** Send a ping/custom payload upstream. */
  send(msg: unknown): void {
    if (this.ws && this.state === 'open') {
      this.ws.send(typeof msg === 'string' ? msg : JSON.stringify(msg))
    }
  }

  // ── Internals ──────────────────────────────────────────────────────

  private normalise(raw: any): WsMessage | null {
    if (!raw || typeof raw !== 'object') return null

    if (raw.channel && raw.event) {
      const key = `${raw.channel}:${raw.event}` in CHANNEL_MAP ? `${raw.channel}:${raw.event}` : raw.channel
      const type = CHANNEL_MAP[key] || raw.channel.replace(':', '_')
      return { type, data: raw.data ?? raw, timestamp: raw.timestamp }
    }

    if (typeof raw.type === 'string') {
      // Backend sometimes wraps payload under .data / .strategy / .signal / .position / .state / .order — normalise.
      const data =
        raw.data ?? raw.strategy ?? raw.signal ?? raw.position ?? raw.state ?? raw.order ?? raw.error ?? raw
      return { type: raw.type, data, timestamp: raw.timestamp }
    }

    return null
  }

  private route(msg: WsMessage): void {
    const throttle = THROTTLE_MS[msg.type] ?? 0
    if (throttle === 0) {
      this.dispatch(msg)
      return
    }

    const now = Date.now()
    const last = this.lastDispatchAt.get(msg.type) ?? 0
    const elapsed = now - last

    if (elapsed >= throttle) {
      this.dispatch(msg)
      this.lastDispatchAt.set(msg.type, now)
      return
    }

    this.pending.set(msg.type, msg)
    if (!this.throttleTimers.has(msg.type)) {
      const timer = window.setTimeout(() => {
        const p = this.pending.get(msg.type)
        if (p) {
          this.dispatch(p)
          this.lastDispatchAt.set(msg.type, Date.now())
          this.pending.delete(msg.type)
        }
        this.throttleTimers.delete(msg.type)
      }, throttle - elapsed)
      this.throttleTimers.set(msg.type, timer)
    }
  }

  private dispatch(msg: WsMessage): void {
    const set = this.handlers.get(msg.type)
    if (!set) return
    for (const h of set) {
      try {
        h(msg.data)
      } catch (e) {
        console.error(`[ws] handler error for ${msg.type}`, e)
      }
    }
  }

  private setState(state: ConnectionState): void {
    if (this.state === state) return
    this.state = state
    const info = { attempt: this.reconnectAttempts, lastMessageAt: this.lastMessageAt }
    for (const h of this.stateHandlers) {
      try {
        h(state, info)
      } catch (e) {
        console.error('[ws] state handler error', e)
      }
    }
  }

  private scheduleReconnect(): void {
    if (this.intentionallyClosed) return
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.warn(`[ws] gave up after ${this.reconnectAttempts} attempts`)
      return
    }
    this.reconnectAttempts++
    const delay = Math.min(
      this.baseDelayMs * Math.pow(2, this.reconnectAttempts - 1),
      this.maxDelayMs,
    )
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private getCookie(name: string): string | null {
    const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`))
    return match ? decodeURIComponent(match[1]) : null
  }
}

export const wsManager = new WebSocketManager()
