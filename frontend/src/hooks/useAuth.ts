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
    onSuccess: () => {
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
