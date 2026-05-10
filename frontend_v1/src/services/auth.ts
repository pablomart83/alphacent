import axios from 'axios';
import type { AuthResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export interface UserPermissions {
  pages: string[];
  actions: string[];
}

export interface UserInfo {
  username: string;
  role: string;
  permissions: UserPermissions;
}

export const authService = {
  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await axios.post<{
      success: boolean;
      message: string;
      username?: string;
      role?: string;
      permissions?: UserPermissions;
    }>(
      `${API_BASE_URL}/auth/login`,
      { username, password },
      { withCredentials: true, timeout: 5000 }
    );

    if (!response.data.success || !response.data.username) {
      throw new Error(response.data.message || 'Login failed');
    }

    // Store user info in localStorage
    localStorage.setItem('username', response.data.username);
    localStorage.setItem('role', response.data.role || 'viewer');
    localStorage.setItem('permissions', JSON.stringify(response.data.permissions || {}));

    return {
      token: 'session',
      user: {
        username: response.data.username,
        role: response.data.role || 'viewer',
        permissions: response.data.permissions || { pages: [], actions: [] },
      },
    };
  },

  async logout(): Promise<void> {
    try {
      await axios.post(`${API_BASE_URL}/auth/logout`, {}, { withCredentials: true, timeout: 5000 });
    } finally {
      localStorage.removeItem('username');
      localStorage.removeItem('role');
      localStorage.removeItem('permissions');
    }
  },

  async checkStatus(): Promise<boolean> {
    try {
      const response = await axios.get<{
        authenticated: boolean;
        username?: string;
        role?: string;
        permissions?: UserPermissions;
      }>(`${API_BASE_URL}/auth/status`, { withCredentials: true, timeout: 5000 });

      if (response.data.authenticated && response.data.username) {
        // Refresh stored role/permissions from server
        localStorage.setItem('username', response.data.username);
        localStorage.setItem('role', response.data.role || 'viewer');
        localStorage.setItem('permissions', JSON.stringify(response.data.permissions || {}));
        return true;
      }
      return false;
    } catch {
      return false;
    }
  },

  getToken(): string | null {
    return localStorage.getItem('username') ? 'session' : null;
  },

  getUsername(): string | null {
    return localStorage.getItem('username');
  },

  getRole(): string {
    return localStorage.getItem('role') || 'viewer';
  },

  getPermissions(): UserPermissions {
    try {
      return JSON.parse(localStorage.getItem('permissions') || '{}');
    } catch {
      return { pages: [], actions: [] };
    }
  },

  hasAction(action: string): boolean {
    const perms = this.getPermissions();
    return perms.actions?.includes(action) ?? false;
  },

  hasPage(page: string): boolean {
    const perms = this.getPermissions();
    return perms.pages?.includes(page) ?? false;
  },

  isAdmin(): boolean {
    return this.getRole() === 'admin';
  },

  isAuthenticated(): boolean {
    return !!this.getToken();
  },
};
