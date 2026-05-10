import { Navigate, useLocation } from 'react-router-dom'
import { Spinner } from '@/components/primitives'
import { useAuthStatus } from '@/hooks/useAuth'

interface ProtectedRouteProps {
  children: React.ReactNode
}

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const location = useLocation()
  const { data, isLoading, isError } = useAuthStatus()

  if (isLoading) {
    return (
      <div className="flex h-screen w-screen items-center justify-center bg-[var(--bg-0)]">
        <Spinner size="lg" />
      </div>
    )
  }

  if (isError || !data?.authenticated) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  return <>{children}</>
}
