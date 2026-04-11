import { BrowserRouter as Router, Routes, Route, Navigate } from 'react-router-dom';
import { useState, useEffect, useRef, lazy, Suspense } from 'react';
import { authService } from './services/auth';
import { wsManager } from './services/websocket';
import { Login } from './pages/Login';
import { ProtectedRoute } from './components/ProtectedRoute';
import { ErrorBoundary } from './components/loading';
import { LoadingOverlay } from './components/loading';
import { PageErrorBoundary } from './components/PageErrorBoundary';
import { TradingModeProvider } from './contexts/TradingModeContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { CommandPalette } from './components/CommandPalette';
import { Toaster, toast } from 'sonner';

// Lazy load all pages for code splitting
const Overview = lazy(() => import('./pages/OverviewNew').then(m => ({ default: m.OverviewNew })));
const Portfolio = lazy(() => import('./pages/PortfolioNew').then(m => ({ default: m.PortfolioNew })));
const OrdersPage = lazy(() => import('./pages/OrdersNew').then(m => ({ default: m.OrdersNew })));
const StrategiesPage = lazy(() => import('./pages/StrategiesNew').then(m => ({ default: m.StrategiesNew })));
const Autonomous = lazy(() => import('./pages/AutonomousNew').then(m => ({ default: m.AutonomousNew })));
const Risk = lazy(() => import('./pages/RiskNew').then(m => ({ default: m.RiskNew })));
const Analytics = lazy(() => import('./pages/AnalyticsNew').then(m => ({ default: m.AnalyticsNew })));
const DataManagement = lazy(() => import('./pages/DataManagementNew').then(m => ({ default: m.DataManagementNew })));
const Settings = lazy(() => import('./pages/SettingsNew').then(m => ({ default: m.SettingsNew })));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then(m => ({ default: m.WatchlistPage })));
const PositionDetail = lazy(() => import('./pages/PositionDetailView').then(m => ({ default: m.PositionDetailView })));
const SystemHealth = lazy(() => import('./pages/SystemHealthPage').then(m => ({ default: m.SystemHealthPage })));
const AuditLog = lazy(() => import('./pages/AuditLogPage').then(m => ({ default: m.AuditLogPage })));

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const validationDone = useRef(false);

  useEffect(() => {
    const checkAuth = async () => {
      const username = localStorage.getItem('username');
      if (username) {
        // Show loading indicator while validating session
        setIsValidating(true);
        setIsLoading(false);

        // Race: checkStatus vs 2-second timeout
        const timeoutPromise = new Promise<boolean>((resolve) =>
          setTimeout(() => resolve(false), 2000)
        );

        try {
          const isValid = await Promise.race([
            authService.checkStatus(),
            timeoutPromise,
          ]);

          if (!validationDone.current) {
            validationDone.current = true;
            if (isValid) {
              setIsAuthenticated(true);
            } else {
              localStorage.removeItem('username');
              setIsAuthenticated(false);
              toast.error('Session expired');
            }
            setIsValidating(false);
          }
        } catch {
          if (!validationDone.current) {
            validationDone.current = true;
            localStorage.removeItem('username');
            setIsAuthenticated(false);
            toast.error('Session expired');
            setIsValidating(false);
          }
        }
        return;
      }
      
      // No cached session — show login page
      setIsLoading(false);
    };

    checkAuth();
  }, []);

  // Establish WebSocket connection when authenticated
  useEffect(() => {
    if (isAuthenticated) {
      console.log('🔌 Establishing WebSocket connection...');
      wsManager.connect();

      return () => {
        console.log('🔌 Disconnecting WebSocket...');
        wsManager.disconnect();
      };
    }
  }, [isAuthenticated]);

  const handleLogin = () => {
    setIsAuthenticated(true);
  };

  const handleLogout = async () => {
    wsManager.disconnect();
    try {
      await authService.logout();
    } catch {
      // Ignore logout API errors
    }
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    localStorage.removeItem('permissions');
    setIsAuthenticated(false);
    validationDone.current = false;
    window.location.href = '/login';
  };

  if (isLoading || isValidating) {
    return (
      <div 
        className="min-h-screen flex items-center justify-center" 
        style={{ backgroundColor: 'var(--color-dark-bg)' }}
      >
        <LoadingOverlay message={isValidating ? "Verifying session..." : "Initializing AlphaCent..."} />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <ThemeProvider>
      <TradingModeProvider>
        <NotificationProvider>
          <Toaster 
            position="top-right" 
            richColors 
            theme="dark"
            offset="16px"
            toastOptions={{
              style: {
                background: '#1f2937',
                border: '1px solid #374151',
                color: '#f3f4f6',
                minWidth: '300px',
              },
            }}
          />
          <Router>
            {/* Toast notifications handled by Sonner <Toaster> above */}
            {isAuthenticated && <CommandPalette />}
            
            <Routes>
            <Route 
              path="/login" 
              element={
                isAuthenticated ? (
                  <Navigate to="/" replace />
                ) : (
                  <Login onLogin={handleLogin} />
                )
              } 
            />
            <Route 
              path="/" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading overview..." />}>
                    <PageErrorBoundary pageName="Overview">
                      <Overview onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/portfolio" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading portfolio..." />}>
                    <PageErrorBoundary pageName="Portfolio">
                      <Portfolio onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/portfolio/:symbol" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading position detail..." />}>
                    <PageErrorBoundary pageName="Position Detail">
                      <PositionDetail onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/orders" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading orders..." />}>
                    <PageErrorBoundary pageName="Orders">
                      <OrdersPage onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/strategies" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading strategies..." />}>
                    <PageErrorBoundary pageName="Strategies">
                      <StrategiesPage onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/autonomous" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading autonomous..." />}>
                    <PageErrorBoundary pageName="Autonomous">
                      <Autonomous onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/risk" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading risk..." />}>
                    <PageErrorBoundary pageName="Risk">
                      <Risk onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/analytics" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading analytics..." />}>
                    <PageErrorBoundary pageName="Analytics">
                      <Analytics onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/data" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading data management..." />}>
                    <PageErrorBoundary pageName="Data Management">
                      <DataManagement onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/watchlist" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading watchlist..." />}>
                    <PageErrorBoundary pageName="Watchlist">
                      <WatchlistPage onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/settings" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading settings..." />}>
                    <PageErrorBoundary pageName="Settings">
                      <Settings onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/system-health" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading system health..." />}>
                    <PageErrorBoundary pageName="System Health">
                      <SystemHealth onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route 
              path="/audit-log" 
              element={
                <ProtectedRoute>
                  <Suspense fallback={<LoadingOverlay message="Loading audit log..." />}>
                    <PageErrorBoundary pageName="Audit Log">
                      <AuditLog onLogout={handleLogout} />
                    </PageErrorBoundary>
                  </Suspense>
                </ProtectedRoute>
              } 
            />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Router>
        </NotificationProvider>
      </TradingModeProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
