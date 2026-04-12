import { type FC, useState, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, LogOut, Sun, Moon, RefreshCw } from 'lucide-react';
import { authService } from '../services/auth';
import { useTheme } from '../contexts/ThemeContext';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { Notifications } from './Notifications';
import { cn } from '../lib/utils';

// Map route paths to permission page names
const PAGE_PERMISSION_MAP: Record<string, string> = {
  '/': 'overview',
  '/portfolio': 'portfolio',
  '/orders': 'orders',
  '/strategies': 'strategies',
  '/autonomous': 'autonomous',
  '/risk': 'risk',
  '/analytics': 'analytics',
  '/data': 'data',
  '/system-health': 'settings',
  '/audit-log': 'settings',
  '/settings': 'settings',
};

interface TopNavBarProps {
  onLogout: () => void;
  onSync?: () => void;
  syncing?: boolean;
  pendingClosuresCount?: number;
  queuedOrdersCount?: number;
}

export const TopNavBar: FC<TopNavBarProps> = ({
  onLogout,
  onSync,
  syncing = false,
  pendingClosuresCount = 0,
  queuedOrdersCount = 0,
}) => {
  const location = useLocation();
  const { theme, toggleTheme } = useTheme();
  const isMobile = useMediaQuery('(max-width: 767px)');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const permissions = authService.getPermissions();
  const allowedPages = permissions.pages || [];
  const username = localStorage.getItem('username') || 'User';
  const role = authService.getRole();

  const allNavItems = [
    { path: '/', label: 'Overview' },
    { path: '/portfolio', label: 'Portfolio', badge: pendingClosuresCount > 0 ? pendingClosuresCount : undefined },
    { path: '/orders', label: 'Orders', badge: queuedOrdersCount > 0 ? queuedOrdersCount : undefined },
    { path: '/strategies', label: 'Strategies' },
    { path: '/autonomous', label: 'Autonomous' },
    { path: '/risk', label: 'Risk' },
    { path: '/analytics', label: 'Analytics' },
    { path: '/data', label: 'Data' },
    { path: '/system-health', label: 'System' },
    { path: '/audit-log', label: 'Audit' },
    { path: '/settings', label: 'Settings' },
  ];

  const navItems = allowedPages.length > 0
    ? allNavItems.filter(item => {
        const pageName = PAGE_PERMISSION_MAP[item.path];
        return !pageName || allowedPages.includes(pageName);
      })
    : allNavItems;

  const isActive = (path: string) => location.pathname === path;

  const closeMobileMenu = useCallback(() => setMobileMenuOpen(false), []);

  return (
    <>
      <nav
        className="flex items-center h-12 max-h-[48px] min-h-[48px] border-b bg-[#0d1117] px-4"
        style={{ borderColor: 'var(--color-dark-border)' }}
      >
        {/* Brand */}
        <Link to="/" className="shrink-0 mr-4">
          <span className="text-lg font-bold text-accent-green font-mono">AlphaCent</span>
        </Link>

        {/* Nav links — desktop */}
        {!isMobile && (
          <div className="flex-1 overflow-x-auto scrollbar-hide">
            <div className="flex items-center gap-1 min-w-max">
              {navItems.map(item => (
                <Link
                  key={item.path}
                  to={item.path}
                  className={cn(
                    'relative px-3 py-1.5 text-xs font-mono whitespace-nowrap transition-colors rounded-sm',
                    isActive(item.path)
                      ? 'text-emerald-400'
                      : 'text-gray-400 hover:text-gray-200'
                  )}
                >
                  {item.label}
                  {item.badge && (
                    <span className="ml-1 bg-amber-500 text-black text-[10px] font-bold rounded-full h-4 min-w-[16px] inline-flex items-center justify-center px-1">
                      {item.badge}
                    </span>
                  )}
                  {isActive(item.path) && (
                    <span className="absolute bottom-0 left-1 right-1 h-0.5 bg-emerald-400 rounded-full" />
                  )}
                </Link>
              ))}
            </div>
          </div>
        )}

        {/* Spacer on mobile */}
        {isMobile && <div className="flex-1" />}

        {/* Right actions */}
        <div className="flex items-center gap-1.5 shrink-0 ml-2">
          <button
            onClick={toggleTheme}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>

          {onSync && (
            <button
              onClick={onSync}
              disabled={syncing}
              className={cn(
                'p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors',
                syncing && 'animate-spin text-accent-green'
              )}
              title="Sync eToro"
            >
              <RefreshCw size={14} />
            </button>
          )}

          <Notifications />

          {/* User dropdown — simplified */}
          <div className="flex items-center gap-2 ml-1 pl-2 border-l border-gray-700">
            <span className="text-xs text-gray-400 font-mono hidden sm:inline">
              {username}
              <span className="text-gray-600 ml-1 capitalize">({role})</span>
            </span>
            <button
              onClick={onLogout}
              className="p-1.5 rounded-md text-gray-400 hover:text-accent-red hover:bg-accent-red/10 transition-colors"
              title="Logout"
            >
              <LogOut size={14} />
            </button>
          </div>

          {/* Hamburger — mobile */}
          {isMobile && (
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors ml-1"
              aria-label="Open menu"
            >
              <Menu size={18} />
            </button>
          )}
        </div>
      </nav>

      {/* Mobile overlay menu */}
      {isMobile && mobileMenuOpen && (
        <div className="fixed inset-0 z-50 bg-[#0d1117] flex flex-col">
          <div className="flex items-center justify-between h-12 px-4 border-b border-gray-800">
            <span className="text-lg font-bold text-accent-green font-mono">AlphaCent</span>
            <button
              onClick={closeMobileMenu}
              className="p-2 rounded-md text-gray-400 hover:text-gray-200"
              aria-label="Close menu"
            >
              <X size={20} />
            </button>
          </div>
          <nav className="flex-1 overflow-y-auto p-4">
            <ul className="space-y-1">
              {navItems.map(item => (
                <li key={item.path}>
                  <Link
                    to={item.path}
                    onClick={closeMobileMenu}
                    className={cn(
                      'flex items-center px-4 py-3 rounded-lg font-mono text-sm transition-colors',
                      isActive(item.path)
                        ? 'bg-emerald-500/10 text-emerald-400 border-l-2 border-emerald-400'
                        : 'text-gray-400 hover:bg-gray-800 hover:text-gray-200'
                    )}
                  >
                    {item.label}
                    {item.badge && (
                      <span className="ml-auto bg-amber-500 text-black text-xs font-bold rounded-full h-5 min-w-[20px] flex items-center justify-center px-1.5">
                        {item.badge}
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
          <div className="p-4 border-t border-gray-800">
            <p className="text-xs text-gray-500 mb-1">Logged in as <span className="text-gray-300 font-mono">{username}</span></p>
            <p className="text-xs text-gray-600 capitalize mb-3">{role}</p>
            <button
              onClick={() => { closeMobileMenu(); onLogout(); }}
              className="w-full px-4 py-2 rounded-lg text-sm font-mono bg-accent-red/10 text-accent-red border border-accent-red/30 hover:bg-accent-red/20 transition-colors"
            >
              Logout
            </button>
          </div>
        </div>
      )}
    </>
  );
};
