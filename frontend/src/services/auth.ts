import axios from 'axios';
import type { AuthResponse } from '../types';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const authService = {
  async login(username: string, password: string): Promise<AuthResponse> {
    const response = await axios.post<{success: boolean, message: string, username?: string}>(
      `${API_BASE_URL}/auth/login`,
      { username, password },
      { withCredentials: true, timeout: 5000 }
    );
    
    if (!response.data.success) {
      throw new Error(response.data.message || 'Login failed');
    }
    
    if (!response.data.username) {
      throw new Error('Invalid response from server');
    }
    
    // Store username in localStorage (backend uses session cookies for auth)
    localStorage.setItem('username', response.data.username);
    
    // Return in expected format
    return {
      token: 'session', // Backend uses session cookies, not tokens
      user: {
        username: response.data.username,
      }
    };
  },

  async logout(): Promise<void> {
    try {
      await axios.post(
        `${API_BASE_URL}/auth/logout`,
        {},
        { withCredentials: true, timeout: 5000 }
      );
    } finally {
      // Clear local storage even if API call fails
      localStorage.removeItem('username');
    }
  },

  async checkStatus(): Promise<boolean> {
    try {
      const response = await axios.get<{authenticated: boolean, username?: string}>(
        `${API_BASE_URL}/auth/status`,
        { withCredentials: true, timeout: 5000 }
      );
      return response.data.authenticated || false;
    } catch {
      return false;
    }
  },

  getToken(): string | null {
    // Backend uses session cookies, not tokens
    return localStorage.getItem('username') ? 'session' : null;
  },

  getUsername(): string | null {
    return localStorage.getItem('username');
  },

  isAuthenticated(): boolean {
    return !!this.getToken();
  },
};
