/**
 * auth-events — tiny pub/sub for authentication-failure notifications.
 *
 * Problem: the API client and WebSocket manager both need to signal the
 * rest of the app when a 401 / close-code 1008 is observed. Neither can
 * import QueryClient directly (circular deps: App owns QueryClient, API
 * client is imported by query factories, etc.).
 *
 * Solution: a module-level callback registry. App.tsx registers one
 * listener that invalidates the auth-status query, clears the query
 * cache, disconnects the WebSocket, and lets React Router's
 * ProtectedRoute redirect to /login.
 *
 * Why not a global event bus? We only need one event type and one
 * listener; a 15-line module is clearer than a dependency.
 */

type AuthErrorReason = 'api-401' | 'ws-1008' | 'ws-4001' | 'status-failed'

type AuthErrorHandler = (reason: AuthErrorReason) => void

let handler: AuthErrorHandler | null = null
let lastFiredAt = 0

/**
 * Rate-limit the auth-error broadcast. When a session dies, 8-12 in-flight
 * queries will all 401 in the same tick. We only need to trigger the
 * redirect once; the rest should be silent.
 */
const MIN_INTERVAL_MS = 2_000

export function setAuthErrorHandler(h: AuthErrorHandler | null): void {
  handler = h
}

export function notifyAuthError(reason: AuthErrorReason): void {
  const now = Date.now()
  if (now - lastFiredAt < MIN_INTERVAL_MS) return
  lastFiredAt = now
  if (handler) {
    try {
      handler(reason)
    } catch (e) {
      // Swallow — auth-error handler misbehaving is not worth crashing the page.
      // eslint-disable-next-line no-console
      console.error('[auth-events] handler threw', e)
    }
  }
}
