import { type FC, type ReactNode, useEffect, useState } from 'react';
import { Navigate } from 'react-router-dom';
import { authService } from '../services/auth';

interface ProtectedRouteProps {
  children: ReactNode;
}

export const ProtectedRoute: FC<ProtectedRouteProps> = ({ children }) => {
  const [isValidating, setIsValidating] = useState(true);
  const [isAuthenticated, setIsAuthenticated] = useState(false);

  useEffect(() => {
    const validateSession = async () => {
      // Check if we have a token in localStorage
      const hasToken = authService.isAuthenticated();
      
      if (!hasToken) {
        setIsAuthenticated(false);
        setIsValidating(false);
        return;
      }

      // Validate session with backend
      const isValid = await authService.checkStatus();
      setIsAuthenticated(isValid);
      
      if (!isValid) {
        // Clear invalid session
        localStorage.removeItem('username');
      }
      
      setIsValidating(false);
    };

    validateSession();
  }, []);

  if (isValidating) {
    return (
      <div 
        className="min-h-screen flex items-center justify-center" 
        style={{ backgroundColor: 'var(--color-dark-bg)' }}
      >
        <div className="text-gray-400">Validating session...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};
