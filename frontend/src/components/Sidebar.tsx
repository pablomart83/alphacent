import { type FC, useState, useEffect, useCallback } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronLeft, ChevronRight, LogOut } from 'lucide-react';
import { authService } from '../services/auth';
import { useMediaQuery } from '../hooks/useMediaQuery';
import {
  Tooltip,
  TooltipTrigger,
  TooltipContent,
  TooltipProvider,
} from './ui/tooltip';

const SIDEBAR_COLLAPSED_KEY = 'alphacent_sidebar_collapsed';

interface SidebarProps {
  onLogout: () => void;
  pendingClosuresCount?: number;
  queuedOrdersCount?: number;
}

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
  '/watchlist': 'watchlist',
  '/system-health': 'settings',
  '/audit-log': 'settings',
  '/settings': 'settings',
};

export const Sidebar: FC<SidebarProps> = ({ onLogout, pendingClosuresCount = 0, queuedOrdersCount = 0 }) => {
  const location = useLocation();
  const permissions = authService.getPermissions();
  const allowedPages = permissions.pages || [];
  const isDesktop = useMediaQuery('(min-width: 1024px)');

  // Initialize collapsed state from localStorage, defaulting to auto-collapse on small screens
  const [collapsed, setCollapsed] = useState<boolean>(() => {
    const stored = localStorage.getItem(SIDEBAR_COLLAPSED_KEY);
    if (stored !== null) return stored === 'true';
    // Default: collapsed on small screens
    return typeof window !== 'undefined' ? window.innerWidth < 1024 : false;
  });

  // Auto-collapse when viewport shrinks below 1024px (if user hasn't manually toggled)
  useEffect(() => {
    if (!isDesktop) {
      setCollapsed(true);
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, 'true');
    }
  }, [isDesktop]);

  const toggleCollapsed = useCallback(() => {
    setCollapsed(prev => {
      const next = !prev;
      localStorage.setItem(SIDEBAR_COLLAPSED_KEY, String(next));
      return next;
    });
  }, []);

  const allNavItems = [
    { path: '/', label: 'Overview', icon: '◆' },
    { path: '/portfolio', label: 'Portfolio', icon: '◇', badge: pendingClosuresCount > 0 ? pendingClosuresCount : undefined },
    { path: '/orders', label: 'Orders', icon: '◈', badge: queuedOrdersCount > 0 ? queuedOrdersCount : undefined },
    { path: '/strategies', label: 'Strategies', icon: '◉' },
    { path: '/autonomous', label: 'Autonomous', icon: '◎' },
    { path: '/risk', label: 'Risk', icon: '◬' },
    { path: '/analytics', label: 'Analytics', icon: '◭' },
    { path: '/data', label: 'Data', icon: '◫' },
    { path: '/watchlist', label: 'Watchlist', icon: '◧' },
    { path: '/system-health', label: 'System', icon: '◍' },
    { path: '/audit-log', label: 'Audit', icon: '◔' },
    { path: '/settings', label: 'Settings', icon: '◐' },
  ];

  // Filter nav items based on user permissions (show all if no permissions loaded yet)
  const navItems = allowedPages.length > 0
    ? allNavItems.filter(item => {
        const pageName = PAGE_PERMISSION_MAP[item.path];
        return !pageName || allowedPages.includes(pageName);
      })
    : allNavItems;

  const isActive = (path: string) => {
    return location.pathname === path;
  };

  return (
    <TooltipProvider delayDuration={200}>
      <aside
        className="h-screen bg-dark-surface border-r border-dark-border flex flex-col transition-all duration-300 ease-in-out"
        style={{ width: collapsed ? 64 : 256, minWidth: collapsed ? 64 : 256 }}
      >
        {/* Logo/Brand + Toggle */}
        <div className="border-b border-dark-border flex items-center justify-between"
          style={{ padding: collapsed ? '16px 12px' : '24px' }}
        >
          {collapsed ? (
            <span className="text-xl font-bold text-accent-green font-mono mx-auto">A</span>
          ) : (
            <div className="min-w-0 flex-1">
              <h1 className="text-2xl font-bold text-accent-green font-mono">
                AlphaCent
              </h1>
              <p className="text-xs text-gray-500 mt-1">Autonomous Trading</p>
            </div>
          )}
          <button
            onClick={toggleCollapsed}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-200 hover:bg-dark-bg transition-colors duration-200 flex-shrink-0"
            aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
          </button>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto" style={{ padding: collapsed ? '8px' : '16px' }}>
          <ul className="space-y-1">
            {navItems.map((item) => {
              const linkContent = (
                <Link
                  to={item.path}
                  className={`
                    flex items-center rounded-lg
                    transition-all duration-200 font-mono text-sm
                    ${collapsed ? 'justify-center px-0 py-3' : 'gap-3 px-4 py-3'}
                    ${
                      isActive(item.path)
                        ? 'bg-accent-green/10 text-accent-green border border-accent-green/30'
                        : 'text-gray-400 hover:bg-dark-bg hover:text-gray-200'
                    }
                  `}
                >
                  <span className="text-lg flex-shrink-0">{item.icon}</span>
                  {!collapsed && (
                    <>
                      <span className="truncate">{item.label}</span>
                      {item.badge && (
                        <span className="ml-auto bg-amber-500 text-black text-xs font-bold rounded-full h-5 min-w-[20px] flex items-center justify-center px-1.5">
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                  {collapsed && item.badge && (
                    <span className="absolute -top-1 -right-1 bg-amber-500 text-black text-[10px] font-bold rounded-full h-4 min-w-[16px] flex items-center justify-center px-1">
                      {item.badge}
                    </span>
                  )}
                </Link>
              );

              if (collapsed) {
                return (
                  <li key={item.path} className="relative">
                    <Tooltip>
                      <TooltipTrigger asChild>
                        {linkContent}
                      </TooltipTrigger>
                      <TooltipContent side="right" className="min-w-0 !min-w-0" style={{ minWidth: 'auto' }}>
                        <span className="font-mono text-sm">{item.label}</span>
                        {item.badge && (
                          <span className="ml-2 bg-amber-500 text-black text-xs font-bold rounded-full px-1.5 py-0.5">
                            {item.badge}
                          </span>
                        )}
                      </TooltipContent>
                    </Tooltip>
                  </li>
                );
              }

              return <li key={item.path}>{linkContent}</li>;
            })}
          </ul>
        </nav>

        {/* User Section */}
        <div className="border-t border-dark-border" style={{ padding: collapsed ? '8px' : '16px' }}>
          {!collapsed && (
            <div className="mb-3 px-4">
              <p className="text-xs text-gray-500">Logged in as</p>
              <p className="text-sm text-gray-300 font-mono truncate">
                {localStorage.getItem('username') || 'User'}
              </p>
              <p className="text-xs text-gray-500 mt-0.5 capitalize">
                {authService.getRole()}
              </p>
            </div>
          )}
          {collapsed ? (
            <Tooltip>
              <TooltipTrigger asChild>
                <button
                  onClick={onLogout}
                  className="w-full flex items-center justify-center p-3 rounded-lg text-accent-red bg-accent-red/10 border border-accent-red/30 hover:bg-accent-red/20 transition-all duration-200"
                  aria-label="Logout"
                >
                  <LogOut size={16} />
                </button>
              </TooltipTrigger>
              <TooltipContent side="right" className="min-w-0 !min-w-0" style={{ minWidth: 'auto' }}>
                <span className="font-mono text-sm">Logout</span>
              </TooltipContent>
            </Tooltip>
          ) : (
            <button
              onClick={onLogout}
              className="
                w-full px-4 py-2 rounded-lg text-sm font-mono
                bg-accent-red/10 text-accent-red border border-accent-red/30
                hover:bg-accent-red/20 transition-all duration-200
              "
            >
              Logout
            </button>
          )}
        </div>
      </aside>
    </TooltipProvider>
  );
};
