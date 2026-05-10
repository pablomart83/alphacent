import { api } from './api'

export interface LoginRequest {
  username: string
  password: string
}

export interface SessionStatus {
  authenticated: boolean
  username?: string
  role?: string
  permissions?: {
    pages: string[]
    actions: string[]
  }
}

export const authService = {
  login(req: LoginRequest) {
    return api.post<{ success: boolean; message: string; username?: string; role?: string; permissions?: SessionStatus['permissions'] }>(
      '/auth/login',
      req,
    )
  },
  logout() {
    return api.post<{ success: boolean; message: string }>('/auth/logout')
  },
  status() {
    return api.get<SessionStatus>('/auth/status')
  },
}
