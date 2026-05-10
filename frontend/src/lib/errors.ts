/**
 * Error classification. Every API / WS failure is funnelled through
 * `classifyError` so UI components show a consistent, humane message.
 */

export interface ClassifiedError {
  title: string
  message: string
  retryable: boolean
  isNetwork: boolean
  isAuth: boolean
  isServer: boolean
  status?: number
  raw: unknown
}

export class ApiError extends Error {
  status: number
  body: unknown

  constructor(status: number, message: string, body?: unknown) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

export function classifyError(err: unknown, context?: string): ClassifiedError {
  const ctx = context ? ` (${context})` : ''

  if (err instanceof ApiError) {
    const isAuth = err.status === 401 || err.status === 403
    const isServer = err.status >= 500
    const isNetwork = false
    return {
      title: isAuth
        ? 'Session expired'
        : isServer
          ? 'Server error'
          : 'Request failed',
      message: err.message || `HTTP ${err.status}${ctx}`,
      retryable: isServer || err.status === 408 || err.status === 429,
      isNetwork,
      isAuth,
      isServer,
      status: err.status,
      raw: err,
    }
  }

  if (err instanceof TypeError && /fetch|network/i.test(err.message)) {
    return {
      title: 'Network error',
      message: `Could not reach server${ctx}. Check your connection.`,
      retryable: true,
      isNetwork: true,
      isAuth: false,
      isServer: false,
      raw: err,
    }
  }

  if (err instanceof Error) {
    return {
      title: 'Error',
      message: `${err.message}${ctx}`,
      retryable: false,
      isNetwork: false,
      isAuth: false,
      isServer: false,
      raw: err,
    }
  }

  return {
    title: 'Unknown error',
    message: `An unexpected error occurred${ctx}.`,
    retryable: false,
    isNetwork: false,
    isAuth: false,
    isServer: false,
    raw: err,
  }
}

/**
 * notifyError — the single canonical way to surface a caught error to
 * the operator. Suppresses auth-failure toasts (the /login redirect
 * triggered by the API client's auth-events pipeline carries the
 * message). Everything else gets a toast with classified copy.
 *
 * Usage:
 *   try { await mutation.mutateAsync(...) }
 *   catch (err) { notifyError(err, 'retire live') }
 *
 * Falls back to a console warning when sonner isn't available (tests).
 */

import type { ExternalToast } from 'sonner'

type ToastFn = (message: string, options?: ExternalToast) => void

let toastImpl: { error: ToastFn } | null = null

// Lazy import to avoid making `errors.ts` pull in sonner at test time.
async function getToast(): Promise<{ error: ToastFn } | null> {
  if (toastImpl) return toastImpl
  try {
    const mod = await import('sonner')
    toastImpl = { error: mod.toast.error.bind(mod.toast) as ToastFn }
    return toastImpl
  } catch {
    return null
  }
}

export function notifyError(err: unknown, context?: string): ClassifiedError {
  const info = classifyError(err, context)
  if (info.isAuth) return info
  void getToast().then((t) => {
    if (t) t.error(info.title, { description: info.message })
  })
  return info
}
