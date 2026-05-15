import { Suspense, lazy, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { toast, Toaster } from 'sonner'
import { AppShell } from '@/components/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Spinner } from '@/components/primitives'
import { AUTH_QUERY_KEY } from '@/hooks/useAuth'
import { setAuthErrorHandler } from '@/services/auth-events'
import { wsManager } from '@/services/websocket'

const Command = lazy(() => import('./pages/command/Command').then((m) => ({ default: m.Command })))
const Book = lazy(() => import('./pages/book/Book').then((m) => ({ default: m.Book })))
const Strategies = lazy(() => import('./pages/strategies/Strategies').then((m) => ({ default: m.Strategies })))
const Guard = lazy(() => import('./pages/guard/Guard').then((m) => ({ default: m.Guard })))
const Research = lazy(() => import('./pages/research/Research').then((m) => ({ default: m.Research })))
const Settings = lazy(() => import('./pages/settings/Settings').then((m) => ({ default: m.Settings })))
const Intel = lazy(() => import('./pages/intel/Intel').then((m) => ({ default: m.Intel })))
const Login = lazy(() => import('./pages/Login').then((m) => ({ default: m.Login })))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      refetchOnWindowFocus: false,
      retry: (failureCount, error: any) => {
        // Don't retry auth or not-found errors
        const status = error?.status as number | undefined
        if (status === 401 || status === 403 || status === 404) return false
        return failureCount < 2
      },
    },
  },
})

const PageFallback = () => (
  <div className="flex h-full items-center justify-center">
    <Spinner size="lg" />
  </div>
)

function AppRoutes() {
  return (
    <Routes>
      <Route
        path="/login"
        element={
          <Suspense fallback={<PageFallback />}>
            <Login />
          </Suspense>
        }
      />
      <Route
        element={
          <ProtectedRoute>
            <AppShell />
          </ProtectedRoute>
        }
      >
        <Route
          index
          element={
            <Suspense fallback={<PageFallback />}>
              <Command />
            </Suspense>
          }
        />
        <Route
          path="book/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Book />
            </Suspense>
          }
        />
        <Route
          path="strategies/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Strategies />
            </Suspense>
          }
        />
        <Route
          path="guard/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Guard />
            </Suspense>
          }
        />
        <Route
          path="research/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Research />
            </Suspense>
          }
        />
        <Route
          path="intel/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Intel />
            </Suspense>
          }
        />
        <Route
          path="settings/*"
          element={
            <Suspense fallback={<PageFallback />}>
              <Settings />
            </Suspense>
          }
        />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}

export default function App() {
  useEffect(() => {
    // Single global handler for session-invalidation events fired by the
    // API client (401) or WebSocket (close 1008/4001). Clears all cached
    // queries so the redirect to /login shows no stale data; disconnects
    // the WS so it stops retrying with a dead cookie; invalidates the
    // auth-status query so ProtectedRoute navigates away immediately.
    setAuthErrorHandler((reason) => {
      try {
        wsManager.disconnect()
      } catch {
        /* ignore */
      }
      queryClient.clear()
      queryClient.invalidateQueries({ queryKey: AUTH_QUERY_KEY })
      toast.info('Signed out', {
        description:
          reason === 'api-401'
            ? 'Your session ended. Sign in again to continue.'
            : 'Connection ended. Sign in again to continue.',
      })
    })
    return () => {
      setAuthErrorHandler(null)
    }
  }, [])

  return (
    <ErrorBoundary>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <AppRoutes />
        </BrowserRouter>
        <Toaster
          position="bottom-right"
          theme="dark"
          toastOptions={{
            style: {
              background: 'var(--bg-2)',
              color: 'var(--text-0)',
              border: '1px solid var(--border-default)',
              fontSize: '12px',
            },
          }}
        />
      </QueryClientProvider>
    </ErrorBoundary>
  )
}
