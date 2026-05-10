/**
 * Typed fetch wrapper. Session cookie is sent automatically via
 * `credentials: 'include'`. Every non-2xx response becomes an `ApiError`.
 *
 * On 401, the client emits a single auth-error event (rate-limited to one
 * every 2s) so the app can react once — not once per in-flight query.
 */

import { ApiError } from '@/lib/errors'
import { notifyAuthError } from './auth-events'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

type Method = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE'

interface RequestOptions {
  method?: Method
  params?: Record<string, string | number | boolean | null | undefined>
  body?: unknown
  signal?: AbortSignal
  headers?: Record<string, string>
}

/** Build a query string from a params object, skipping nullish values. */
function buildQuery(params?: RequestOptions['params']): string {
  if (!params) return ''
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v == null) continue
    parts.push(`${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  }
  return parts.length ? `?${parts.join('&')}` : ''
}

export async function request<T = unknown>(
  path: string,
  opts: RequestOptions = {},
): Promise<T> {
  const { method = 'GET', params, body, signal, headers = {} } = opts
  const url = `${API_BASE_URL}${path}${buildQuery(params)}`

  const init: RequestInit = {
    method,
    credentials: 'include',
    signal,
    headers: {
      Accept: 'application/json',
      ...headers,
    },
  }

  if (body !== undefined && body !== null) {
    init.headers = { 'Content-Type': 'application/json', ...init.headers }
    init.body = typeof body === 'string' ? body : JSON.stringify(body)
  }

  const res = await fetch(url, init)

  if (!res.ok) {
    let payload: unknown = null
    try {
      payload = await res.json()
    } catch {
      try {
        payload = await res.text()
      } catch {
        payload = null
      }
    }
    const message =
      (payload && typeof payload === 'object' && 'detail' in payload
        ? String((payload as { detail: unknown }).detail)
        : null) || res.statusText || `HTTP ${res.status}`

    // Broadcast auth failures once. The handler (installed in App.tsx) is
    // responsible for clearing queries, disconnecting the WS, and letting
    // ProtectedRoute redirect to /login — so call sites don't each need
    // to reason about 401s.
    if (res.status === 401) {
      notifyAuthError('api-401')
    }

    throw new ApiError(res.status, message, payload)
  }

  if (res.status === 204) return undefined as T

  const contentType = res.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    return (await res.json()) as T
  }
  return (await res.text()) as unknown as T
}

export const api = {
  get: <T>(path: string, params?: RequestOptions['params'], signal?: AbortSignal) =>
    request<T>(path, { method: 'GET', params, signal }),
  post: <T>(path: string, body?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, { method: 'POST', body, params }),
  put: <T>(path: string, body?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, { method: 'PUT', body, params }),
  patch: <T>(path: string, body?: unknown, params?: RequestOptions['params']) =>
    request<T>(path, { method: 'PATCH', body, params }),
  delete: <T>(path: string, params?: RequestOptions['params']) =>
    request<T>(path, { method: 'DELETE', params }),
}
