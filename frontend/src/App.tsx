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
import { PositionsProvider } from './contexts/PositionsContext';
import { NotificationProvider } from './contexts/NotificationContext';
import { ThemeProvider } from './contexts/ThemeContext';
import { AppShell } from './components/AppShell';
import { CommandPalette } from './components/CommandPalette';
import { Toaster, toast } from 'sonner';

// Lazy load all pages for code splitting
const Overview      = lazy(() => import('./pages/OverviewNew').then(m => ({ default: m.OverviewNew })));
const Portfolio     = lazy(() => import('./pages/PortfolioNew').then(m => ({ default: m.PortfolioNew })));
const OrdersPage    = lazy(() => import('./pages/OrdersNew').then(m => ({ default: m.OrdersNew })));
const StrategiesPage = lazy(() => import('./pages/StrategiesNew').then(m => ({ default: m.StrategiesNew })));
const Autonomous    = lazy(() => import('./pages/AutonomousNew').then(m => ({ default: m.AutonomousNew })));
const Risk          = lazy(() => import('./pages/RiskNew').then(m => ({ default: m.RiskNew })));
const Analytics     = lazy(() => import('./pages/AnalyticsNew').then(m => ({ default: m.AnalyticsNew })));
const DataManagement = lazy(() => import('./pages/DataManagementNew').then(m => ({ default: m.DataManagementNew })));
const Settings      = lazy(() => import('./pages/SettingsNew').then(m => ({ default: m.SettingsNew })));
const WatchlistPage = lazy(() => import('./pages/WatchlistPage').then(m => ({ default: m.WatchlistPage })));
const PositionDetail = lazy(() => import('./pages/PositionDetailView').then(m => ({ default: m.PositionDetailView })));
const SystemHealth  = lazy(() => import('./pages/SystemHealthPage').then(m => ({ default: m.SystemHealthPage })));
const AuditLog      = lazy(() => import('./pages/AuditLogPage').then(m => ({ default: m.AuditLogPage })));

// Wrap a lazy page in Suspense + PageErrorBoundary
function Page({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <Suspense fallback={<LoadingOverlay message={`Loading ${name.toLowerCase()}...`} />}>
      <PageErrorBoundary pageName={name}>
        {children}
      </PageErrorBoundary>
    </Suspense>
  );
}

function App() {
  const [isAuthenticated, setIsAuthenticated] = useState<boolean>(false);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const validationDone = useRef(false);

  useEffect(() => {
    const checkAuth = async () => {
      const username = localStorage.getItem('username');
      if (username) {
        setIsValidating(true);
        setIsLoading(false);
        const timeoutPromise = new Promise<boolean>(resolve => setTimeout(() => resolve(false), 2000));
        try {
          const isValid = await Promise.race([authService.checkStatus(), timeoutPromise]);
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
      setIsLoading(false);
    };
    checkAuth();
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      wsManager.connect();
      return () => { wsManager.disconnect(); };
    }
  }, [isAuthenticated]);

  const handleLogin = () => setIsAuthenticated(true);

  const handleLogout = async () => {
    wsManager.disconnect();
    try { await authService.logout(); } catch {}
    localStorage.removeItem('username');
    localStorage.removeItem('role');
    localStorage.removeItem('permissions');
    setIsAuthenticated(false);
    validationDone.current = false;
    window.location.href = '/login';
  };

  if (isLoading || isValidating) {
    return (
      <div className="min-h-screen flex items-center justify-center" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
        <LoadingOverlay message={isValidating ? 'Verifying session...' : 'Initializing AlphaCent...'} />
      </div>
    );
  }

  return (
    <ErrorBoundary>
      <ThemeProvider>
        <TradingModeProvider>
          <PositionsProvider>
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
                {isAuthenticated && <CommandPalette />}
                <Routes>
                  {/* Public */}
                  <Route
                    path="/login"
                    element={isAuthenticated ? <Navigate to="/" replace /> : <Login onLogin={handleLogin} />}
                  />

                  {/* Authenticated shell — mounts ONCE, survives all navigation */}
                  <Route
                    element={
                      <ProtectedRoute>
                        <AppShell onLogout={handleLogout} />
                      </ProtectedRoute>
                    }
                  >
                    <Route path="/" element={<Page name="Overview"><Overview onLogout={handleLogout} /></Page>} />
                    <Route path="/portfolio" element={<Page name="Portfolio"><Portfolio onLogout={handleLogout} /></Page>} />
                    <Route path="/portfolio/:symbol" element={<Page name="Position Detail"><PositionDetail onLogout={handleLogout} /></Page>} />
                    <Route path="/orders" element={<Page name="Orders"><OrdersPage onLogout={handleLogout} /></Page>} />
                    <Route path="/strategies" element={<Page name="Strategies"><StrategiesPage onLogout={handleLogout} /></Page>} />
                    <Route path="/autonomous" element={<Page name="Autonomous"><Autonomous onLogout={handleLogout} /></Page>} />
                    <Route path="/risk" element={<Page name="Risk"><Risk onLogout={handleLogout} /></Page>} />
                    <Route path="/analytics" element={<Page name="Analytics"><Analytics onLogout={handleLogout} /></Page>} />
                    <Route path="/data" element={<Page name="Data Management"><DataManagement onLogout={handleLogout} /></Page>} />
                    <Route path="/watchlist" element={<Page name="Watchlist"><WatchlistPage onLogout={handleLogout} /></Page>} />
                    <Route path="/settings" element={<Page name="Settings"><Settings onLogout={handleLogout} /></Page>} />
                    <Route path="/system-health" element={<Page name="System Health"><SystemHealth onLogout={handleLogout} /></Page>} />
                    <Route path="/audit-log" element={<Page name="Audit Log"><AuditLog onLogout={handleLogout} /></Page>} />
                  </Route>

                  <Route path="*" element={<Navigate to="/" replace />} />
                </Routes>
              </Router>
            </NotificationProvider>
          </PositionsProvider>
        </TradingModeProvider>
      </ThemeProvider>
    </ErrorBoundary>
  );
}

export default App;
