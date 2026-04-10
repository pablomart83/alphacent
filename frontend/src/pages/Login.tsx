import { type FC, useState, type FormEvent } from 'react';
import { useAuth } from '../hooks/useAuth';

interface LoginProps {
  onLogin: () => void;
}

export const Login: FC<LoginProps> = ({ onLogin }) => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const { login, isLoading, error, clearError } = useAuth();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    clearError();
    if (!username || !password) return;
    const result = await login(username, password);
    if (result) onLogin();
  };

  return (
    <div style={{
      minHeight: '100vh',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      background: 'linear-gradient(135deg, #0a0e1a 0%, #111827 50%, #0a0e1a 100%)',
      fontFamily: '-apple-system, BlinkMacSystemFont, "Inter", "Segoe UI", sans-serif',
    }}>
      <div style={{
        width: '100%',
        maxWidth: '420px',
        padding: '48px 40px',
        background: 'rgba(17, 24, 39, 0.8)',
        border: '1px solid rgba(55, 65, 81, 0.5)',
        borderRadius: '16px',
        backdropFilter: 'blur(20px)',
        boxShadow: '0 25px 50px rgba(0, 0, 0, 0.5)',
      }}>
        {/* Logo & Branding */}
        <div style={{ textAlign: 'center', marginBottom: '40px' }}>
          <div style={{
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            width: '56px',
            height: '56px',
            borderRadius: '12px',
            background: 'linear-gradient(135deg, #3b82f6, #2563eb)',
            marginBottom: '20px',
            fontSize: '24px',
            fontWeight: 700,
            color: '#ffffff',
            letterSpacing: '-1px',
          }}>
            α
          </div>
          <h1 style={{
            fontSize: '28px',
            fontWeight: 700,
            color: '#f9fafb',
            margin: '0 0 8px 0',
            letterSpacing: '-0.5px',
          }}>
            AlphaCent
          </h1>
          <p style={{
            fontSize: '14px',
            color: '#6b7280',
            margin: 0,
            fontWeight: 400,
          }}>
            Autonomous Trading Platform
          </p>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            padding: '12px 16px',
            marginBottom: '24px',
            borderRadius: '8px',
            fontSize: '13px',
            color: '#fca5a5',
            background: 'rgba(239, 68, 68, 0.1)',
            border: '1px solid rgba(239, 68, 68, 0.2)',
          }}>
            {error}
          </div>
        )}

        {/* Form */}
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: '20px' }}>
            <label htmlFor="username" style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: 500,
              color: '#9ca3af',
              marginBottom: '8px',
            }}>
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter username"
              disabled={isLoading}
              required
              autoComplete="username"
              autoFocus
              style={{
                width: '100%',
                padding: '12px 16px',
                fontSize: '14px',
                color: '#f3f4f6',
                background: '#0a0e1a',
                border: '1px solid #1f2937',
                borderRadius: '8px',
                outline: 'none',
                transition: 'border-color 0.2s',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
              onBlur={(e) => e.target.style.borderColor = '#1f2937'}
            />
          </div>

          <div style={{ marginBottom: '28px' }}>
            <label htmlFor="password" style={{
              display: 'block',
              fontSize: '13px',
              fontWeight: 500,
              color: '#9ca3af',
              marginBottom: '8px',
            }}>
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Enter password"
              disabled={isLoading}
              required
              autoComplete="current-password"
              style={{
                width: '100%',
                padding: '12px 16px',
                fontSize: '14px',
                color: '#f3f4f6',
                background: '#0a0e1a',
                border: '1px solid #1f2937',
                borderRadius: '8px',
                outline: 'none',
                transition: 'border-color 0.2s',
                boxSizing: 'border-box',
              }}
              onFocus={(e) => e.target.style.borderColor = '#3b82f6'}
              onBlur={(e) => e.target.style.borderColor = '#1f2937'}
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !username || !password}
            style={{
              width: '100%',
              padding: '12px',
              fontSize: '14px',
              fontWeight: 600,
              color: '#ffffff',
              background: isLoading ? '#1e40af' : 'linear-gradient(135deg, #3b82f6, #2563eb)',
              border: 'none',
              borderRadius: '8px',
              cursor: (!username || !password || isLoading) ? 'not-allowed' : 'pointer',
              opacity: (!username || !password || isLoading) ? 0.5 : 1,
              transition: 'all 0.2s',
              letterSpacing: '0.3px',
            }}
          >
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        {/* Footer */}
        <div style={{
          marginTop: '32px',
          paddingTop: '20px',
          borderTop: '1px solid rgba(55, 65, 81, 0.3)',
          textAlign: 'center',
        }}>
          <p style={{
            fontSize: '12px',
            color: '#4b5563',
            margin: 0,
          }}>
            Secured connection · v1.0.0
          </p>
        </div>
      </div>
    </div>
  );
};
