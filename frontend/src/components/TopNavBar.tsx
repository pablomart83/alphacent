import { type FC, useState, useCallback, useRef, useEffect } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { Menu, X, LogOut, Sun, Moon, RefreshCw, LayoutGrid, Check, Trash2, Save } from 'lucide-react';
import { authService } from '../services/auth';
import { useTheme } from '../contexts/ThemeContext';
import { useMediaQuery } from '../hooks/useMediaQuery';
import { Notifications } from './Notifications';
import { cn } from '../lib/utils';
import {
  getPresets,
  getActivePreset,
  setActivePreset,
  savePreset,
  deletePreset,
  resetToDefault,
} from '../lib/workspace-presets';

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

// ── Workspace Switcher Dropdown ──────────────────────────────────────────────

const WorkspaceSwitcher: FC = () => {
  const [open, setOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveName, setSaveName] = useState('');
  const dropdownRef = useRef<HTMLDivElement>(null);

  const presets = getPresets();
  const activeName = getActivePreset();

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setOpen(false);
        setSaving(false);
      }
    };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  const handleSwitch = (name: string) => {
    setOpen(false);
    setActivePreset(name);
  };

  const handleSave = () => {
    const trimmed = saveName.trim();
    if (!trimmed) return;
    const ok = savePreset(trimmed);
    if (ok) {
      setSaving(false);
      setSaveName('');
      setOpen(false);
    }
  };

  const handleDelete = (e: React.MouseEvent, name: string) => {
    e.stopPropagation();
    deletePreset(name);
    // Force re-render by toggling
    setOpen(false);
    setTimeout(() => setOpen(true), 0);
  };

  const defaults = presets.filter(p => p.isDefault);
  const userPresets = presets.filter(p => !p.isDefault);

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        onClick={() => setOpen(o => !o)}
        className="flex items-center gap-1 px-1.5 py-1 rounded-md text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors text-[11px] font-mono"
        title="Workspace presets"
      >
        <LayoutGrid size={13} />
        <span className="hidden lg:inline max-w-[80px] truncate">
          {activeName ?? 'Custom'}
        </span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 w-56 bg-[#161b22] border border-gray-700 rounded-lg shadow-xl z-50 py-1 text-xs">
          {/* Default presets */}
          <div className="px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider">Defaults</div>
          {defaults.map(p => (
            <button
              key={p.name}
              onClick={() => handleSwitch(p.name)}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-gray-800 transition-colors',
                activeName === p.name ? 'text-emerald-400' : 'text-gray-300'
              )}
            >
              {activeName === p.name && <Check size={12} className="shrink-0" />}
              <span className={activeName === p.name ? '' : 'ml-[20px]'}>{p.name}</span>
            </button>
          ))}

          {/* User presets */}
          {userPresets.length > 0 && (
            <>
              <div className="border-t border-gray-700 my-1" />
              <div className="px-2 py-1 text-[10px] text-gray-500 uppercase tracking-wider">Saved</div>
              {userPresets.map(p => (
                <button
                  key={p.name}
                  onClick={() => handleSwitch(p.name)}
                  className={cn(
                    'w-full flex items-center gap-2 px-3 py-1.5 text-left hover:bg-gray-800 transition-colors group',
                    activeName === p.name ? 'text-emerald-400' : 'text-gray-300'
                  )}
                >
                  {activeName === p.name && <Check size={12} className="shrink-0" />}
                  <span className={cn('flex-1 truncate', activeName === p.name ? '' : 'ml-[20px]')}>{p.name}</span>
                  <span
                    onClick={(e) => handleDelete(e, p.name)}
                    className="opacity-0 group-hover:opacity-100 p-0.5 rounded hover:bg-red-500/20 hover:text-red-400 transition-all shrink-0"
                    title="Delete preset"
                  >
                    <Trash2 size={11} />
                  </span>
                </button>
              ))}
            </>
          )}

          {/* Actions */}
          <div className="border-t border-gray-700 my-1" />

          {saving ? (
            <div className="px-3 py-1.5 flex items-center gap-1.5">
              <input
                autoFocus
                value={saveName}
                onChange={e => setSaveName(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') handleSave(); if (e.key === 'Escape') setSaving(false); }}
                placeholder="Preset name…"
                className="flex-1 bg-gray-800 border border-gray-600 rounded px-2 py-1 text-xs text-gray-200 outline-none focus:border-emerald-500"
                maxLength={20}
              />
              <button
                onClick={handleSave}
                className="p-1 rounded bg-emerald-600 hover:bg-emerald-500 text-white transition-colors"
                title="Save"
              >
                <Check size={12} />
              </button>
            </div>
          ) : (
            <button
              onClick={() => setSaving(true)}
              className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
            >
              <Save size={12} />
              Save Current
            </button>
          )}

          <button
            onClick={() => { setOpen(false); resetToDefault(); }}
            className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-gray-400 hover:text-gray-200 hover:bg-gray-800 transition-colors"
          >
            <RefreshCw size={12} />
            Reset to Default
          </button>
        </div>
      )}
    </div>
  );
};

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
          <WorkspaceSwitcher />

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
