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

    if (!username || !password) {
      return;
    }

    const result = await login(username, password);
    if (result) {
      onLogin();
    }
  };

  return (
    <div 
      className="min-h-screen flex items-center justify-center px-4" 
      style={{ backgroundColor: 'var(--color-dark-bg)' }}
    >
      <div 
        className="p-8 rounded-lg border max-w-md w-full" 
        style={{ 
          backgroundColor: 'var(--color-dark-surface)', 
          borderColor: 'var(--color-dark-border)' 
        }}
      >
        <div className="mb-8 text-center">
          <h1 
            className="text-3xl font-bold mb-2 whitespace-normal"
            style={{ color: 'var(--color-text-primary)' }}
          >
            AlphaCent
          </h1>
          <p 
            className="text-sm whitespace-normal"
            style={{ color: 'var(--color-text-secondary)' }}
          >
            Autonomous Trading Platform
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-6">
          {error && (
            <div 
              className="p-3 rounded text-sm border whitespace-normal break-words"
              style={{ 
                backgroundColor: 'rgba(239, 68, 68, 0.1)',
                borderColor: 'var(--color-accent-red)',
                color: 'var(--color-accent-red)'
              }}
            >
              {error}
            </div>
          )}

          <div>
            <label 
              htmlFor="username" 
              className="block text-sm font-medium mb-2"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="login-input"
              placeholder="Enter username"
              disabled={isLoading}
              required
            />
          </div>

          <div>
            <label 
              htmlFor="password" 
              className="block text-sm font-medium mb-2"
              style={{ color: 'var(--color-text-secondary)' }}
            >
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="login-input"
              placeholder="Enter password"
              disabled={isLoading}
              required
            />
          </div>

          <button
            type="submit"
            disabled={isLoading || !username || !password}
            className="w-full py-3 rounded font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90"
            style={{ 
              backgroundColor: 'var(--color-accent-blue)',
              color: '#ffffff'
            }}
          >
            {isLoading ? 'Logging in...' : 'Login'}
          </button>
        </form>

        <div className="mt-6 text-center text-sm">
          <p 
            className="whitespace-normal"
            style={{ color: 'var(--color-text-tertiary)' }}
          >
            Demo credentials: admin / admin123
          </p>
        </div>
      </div>
    </div>
  );
};
