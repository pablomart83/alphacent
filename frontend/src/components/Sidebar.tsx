import { type FC } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { authService } from '../services/auth';

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
  '/settings': 'settings',
};

export const Sidebar: FC<SidebarProps> = ({ onLogout, pendingClosuresCount = 0, queuedOrdersCount = 0 }) => {
  const location = useLocation();
  const permissions = authService.getPermissions();
  const allowedPages = permissions.pages || [];

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
    <aside className="w-64 h-screen bg-dark-surface border-r border-dark-border flex flex-col">
      {/* Logo/Brand */}
      <div className="p-6 border-b border-dark-border">
        <h1 className="text-2xl font-bold text-accent-green font-mono">
          AlphaCent
        </h1>
        <p className="text-xs text-gray-500 mt-1">Autonomous Trading</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.path}>
              <Link
                to={item.path}
                className={`
                  flex items-center gap-3 px-4 py-3 rounded-lg
                  transition-all duration-200 font-mono text-sm
                  ${
                    isActive(item.path)
                      ? 'bg-accent-green/10 text-accent-green border border-accent-green/30'
                      : 'text-gray-400 hover:bg-dark-bg hover:text-gray-200'
                  }
                `}
              >
                <span className="text-lg">{item.icon}</span>
                <span>{item.label}</span>
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

      {/* User Section */}
      <div className="p-4 border-t border-dark-border">
        <div className="mb-3 px-4">
          <p className="text-xs text-gray-500">Logged in as</p>
          <p className="text-sm text-gray-300 font-mono">
            {localStorage.getItem('username') || 'User'}
          </p>
          <p className="text-xs text-gray-500 mt-0.5 capitalize">
            {authService.getRole()}
          </p>
        </div>
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
      </div>
    </aside>
  );
};
