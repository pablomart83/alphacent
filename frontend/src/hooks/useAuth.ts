import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { authService, type SessionStatus } from '@/services/auth'

export const AUTH_QUERY_KEY = ['auth', 'status'] as const

export function useAuthStatus() {
  return useQuery<SessionStatus>({
    queryKey: AUTH_QUERY_KEY,
    queryFn: () => authService.status(),
    staleTime: 60_000,
    refetchOnWindowFocus: true,
  })
}

export function useLogin() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: authService.login,
    onSuccess: (data) => {
      // Seed the auth-status cache immediately with the data we already have
      // from the login response. This prevents the isLoading gap between
      // navigate() and the /auth/status refetch, which was the window where
      // a stale 401 from a queued retry could fire notifyAuthError and wipe
      // the freshly-set session — causing the double-login prompt.
      if (data.username) {
        qc.setQueryData<SessionStatus>(AUTH_QUERY_KEY, {
          authenticated: true,
          username: data.username,
          role: data.role,
          permissions: data.permissions,
        })
      }
      // Still invalidate so a background refetch confirms the session with
      // the server, but the cache is already warm so ProtectedRoute won't
      // flash a loading spinner or redirect.
      qc.invalidateQueries({ queryKey: AUTH_QUERY_KEY })
    },
  })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: authService.logout,
    onSuccess: () => {
      qc.clear()
    },
  })
}
