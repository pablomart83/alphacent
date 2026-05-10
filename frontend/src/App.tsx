import { Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { AppShell } from '@/components/AppShell'
import { ProtectedRoute } from '@/components/ProtectedRoute'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { Spinner } from '@/components/primitives'

const Command = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Command" sprint={1} /> })))
const Book = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Book" sprint={2} description="Positions, orders, execution quality, live account — unified surface." /> })))
const Strategies = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Strategies" sprint={5} description="Library, cycle, templates, symbols, graduation, lab." /> })))
const Guard = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Guard" sprint={8} description="Risk, gates, system health, circuit breakers, alerts, audit." /> })))
const Research = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Research" sprint={10} description="Performance, attribution, regime, tear sheet, stress, journal." /> })))
const Settings = lazy(() => import('./pages/ComingSoon').then((m) => ({ default: () => <m.ComingSoon surface="Settings" sprint={12} /> })))
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
