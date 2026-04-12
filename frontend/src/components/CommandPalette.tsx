import { type FC, useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import * as DialogPrimitive from '@radix-ui/react-dialog';
import { Search, ArrowRight, Clock, Command } from 'lucide-react';
import { useFuzzySearch, type SearchableItem, type FuzzySearchResult } from '../hooks/useFuzzySearch';
import { useTradingMode } from '../contexts/TradingModeContext';
import { apiClient } from '../services/api';
import { cn } from '../lib/utils';

// ── Constants ──────────────────────────────────────────────────────────────

const RECENT_ITEMS_KEY = 'alphacent_command_palette_recent';
const MAX_RECENT = 5;

const CATEGORY_LABELS: Record<string, string> = {
  symbol: 'Symbols',
  strategy: 'Strategies',
  page: 'Pages',
  action: 'Actions',
};

const CATEGORY_ORDER = ['page', 'symbol', 'strategy', 'action'];

const PAGE_ITEMS: Omit<SearchableItem, 'action'>[] = [
  { id: 'page-overview', type: 'page', label: 'Overview', description: 'Command Centre', icon: '◆' },
  { id: 'page-portfolio', type: 'page', label: 'Portfolio', description: 'Positions & holdings', icon: '◇' },
  { id: 'page-orders', type: 'page', label: 'Orders', description: 'Order management', icon: '◈' },
  { id: 'page-strategies', type: 'page', label: 'Strategies', description: 'Strategy management', icon: '◉' },
  { id: 'page-autonomous', type: 'page', label: 'Autonomous', description: 'Autonomous trading', icon: '◎' },
  { id: 'page-risk', type: 'page', label: 'Risk', description: 'Risk management', icon: '◬' },
  { id: 'page-analytics', type: 'page', label: 'Analytics', description: 'Performance analytics', icon: '◭' },
  { id: 'page-data', type: 'page', label: 'Data Management', description: 'Data pipeline', icon: '◫' },
  { id: 'page-watchlist', type: 'page', label: 'Watchlist', description: 'Symbol watchlist', icon: '◧' },
  { id: 'page-system-health', type: 'page', label: 'System Health', description: 'Service monitoring', icon: '◍' },
  { id: 'page-audit-log', type: 'page', label: 'Audit Log', description: 'Decision trail', icon: '◔' },
  { id: 'page-settings', type: 'page', label: 'Settings', description: 'Configuration', icon: '◐' },
];

const PAGE_ROUTES: Record<string, string> = {
  'page-overview': '/',
  'page-portfolio': '/portfolio',
  'page-orders': '/orders',
  'page-strategies': '/strategies',
  'page-autonomous': '/autonomous',
  'page-risk': '/risk',
  'page-analytics': '/analytics',
  'page-data': '/data',
  'page-watchlist': '/watchlist',
  'page-system-health': '/system-health',
  'page-audit-log': '/audit-log',
  'page-settings': '/settings',
};

// ── Recent items persistence ───────────────────────────────────────────────

interface RecentEntry {
  id: string;
  label: string;
  type: SearchableItem['type'];
  timestamp: number;
}

function getRecentItems(): RecentEntry[] {
  try {
    const raw = localStorage.getItem(RECENT_ITEMS_KEY);
    if (!raw) return [];
    return JSON.parse(raw) as RecentEntry[];
  } catch {
    return [];
  }
}

function addRecentItem(item: SearchableItem) {
  const recents = getRecentItems().filter((r) => r.id !== item.id);
  recents.unshift({ id: item.id, label: item.label, type: item.type, timestamp: Date.now() });
  localStorage.setItem(RECENT_ITEMS_KEY, JSON.stringify(recents.slice(0, MAX_RECENT)));
}

// ── Component ──────────────────────────────────────────────────────────────

interface CommandPaletteProps {}

export const CommandPalette: FC<CommandPaletteProps> = () => {
  const navigate = useNavigate();
  const { tradingMode } = useTradingMode();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [symbols, setSymbols] = useState<string[]>([]);
  const [strategies, setStrategies] = useState<Array<{ id: string; name: string }>>([]);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  // Fetch symbols and strategies for search
  useEffect(() => {
    if (!open || !tradingMode) return;
    let cancelled = false;

    const load = async () => {
      try {
        const [positions, strats] = await Promise.all([
          apiClient.getPositions(tradingMode).catch(() => []),
          apiClient.getStrategies(tradingMode, true).catch(() => []),
        ]);
        if (cancelled) return;

        // Deduplicate symbols from positions
        const syms = Array.from(new Set(positions.map((p) => p.symbol).filter(Boolean)));
        setSymbols(syms);
        setStrategies(
          strats.map((s) => ({ id: s.id?.toString() || '', name: s.name || '' })),
        );
      } catch {
        // Silently fail — palette still works with pages + actions
      }
    };

    load();
    return () => { cancelled = true; };
  }, [open, tradingMode]);

  // Build searchable items
  const allItems: SearchableItem[] = useMemo(() => {
    const items: SearchableItem[] = [];

    // Pages
    for (const p of PAGE_ITEMS) {
      items.push({
        ...p,
        action: () => {
          navigate(PAGE_ROUTES[p.id] || '/');
        },
      });
    }

    // Symbols → navigate to /portfolio/:symbol
    for (const sym of symbols) {
      items.push({
        id: `symbol-${sym}`,
        type: 'symbol',
        label: sym,
        description: 'Navigate to position detail',
        icon: '📈',
        action: () => navigate(`/portfolio/${sym}`),
      });
    }

    // Strategies → navigate to /strategies
    for (const s of strategies) {
      items.push({
        id: `strategy-${s.id}`,
        type: 'strategy',
        label: s.name,
        description: 'View strategy',
        icon: '◉',
        action: () => navigate('/strategies'),
      });
    }

    // Actions
    items.push({
      id: 'action-sync',
      type: 'action',
      label: 'Sync Positions',
      description: 'Trigger eToro position sync',
      icon: '🔄',
      action: () => {
        if (tradingMode) {
          apiClient.syncPositions(tradingMode).catch(() => {});
        }
      },
    });
    items.push({
      id: 'action-sync-orders',
      type: 'action',
      label: 'Sync Orders',
      description: 'Trigger eToro order sync',
      icon: '🔄',
      action: () => {
        if (tradingMode) {
          apiClient.syncOrders(tradingMode).catch(() => {});
        }
      },
    });

    return items;
  }, [symbols, strategies, tradingMode, navigate]);

  const { searchGrouped } = useFuzzySearch(allItems);

  // Compute visible results
  const grouped = useMemo(() => {
    if (!query.trim()) return null;
    return searchGrouped(query);
  }, [query, searchGrouped]);

  // Flat list for keyboard navigation
  const flatResults: SearchableItem[] = useMemo(() => {
    if (!grouped) return [];
    const flat: SearchableItem[] = [];
    for (const cat of CATEGORY_ORDER) {
      if (grouped[cat]) {
        for (const r of grouped[cat]) flat.push(r.item);
      }
    }
    return flat;
  }, [grouped]);

  // Recent items when query is empty
  const recentItems = useMemo(() => {
    if (query.trim()) return [];
    const recents = getRecentItems();
    return recents
      .map((r) => allItems.find((item) => item.id === r.id))
      .filter(Boolean) as SearchableItem[];
  }, [query, allItems]);

  const visibleItems = query.trim() ? flatResults : recentItems;

  // Reset selection when results change
  useEffect(() => {
    setSelectedIndex(0);
  }, [query]);

  // Execute selected item
  const executeItem = useCallback(
    (item: SearchableItem) => {
      addRecentItem(item);
      item.action();
      setOpen(false);
      setQuery('');
    },
    [],
  );

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.min(prev + 1, visibleItems.length - 1));
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedIndex((prev) => Math.max(prev - 1, 0));
      } else if (e.key === 'Enter') {
        e.preventDefault();
        if (visibleItems[selectedIndex]) {
          executeItem(visibleItems[selectedIndex]);
        }
      }
    },
    [visibleItems, selectedIndex, executeItem],
  );

  // Scroll selected item into view
  useEffect(() => {
    if (!listRef.current) return;
    const el = listRef.current.querySelector(`[data-index="${selectedIndex}"]`);
    if (el) el.scrollIntoView({ block: 'nearest' });
  }, [selectedIndex]);

  // Global Ctrl+K / Cmd+K handler
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        setOpen((prev) => !prev);
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Reset state when dialog closes
  useEffect(() => {
    if (!open) {
      setQuery('');
      setSelectedIndex(0);
    }
  }, [open]);

  // Build grouped sections for rendering
  const sections = useMemo(() => {
    if (!query.trim()) {
      if (recentItems.length === 0) return [];
      return [{ label: 'Recent', items: recentItems }];
    }
    if (!grouped) return [];
    const result: Array<{ label: string; items: SearchableItem[] }> = [];
    for (const cat of CATEGORY_ORDER) {
      if (grouped[cat] && grouped[cat].length > 0) {
        result.push({
          label: CATEGORY_LABELS[cat] || cat,
          items: grouped[cat].map((r: FuzzySearchResult) => r.item),
        });
      }
    }
    return result;
  }, [query, grouped, recentItems]);

  // Track flat index across sections
  let flatIndex = 0;

  return (
    <DialogPrimitive.Root open={open} onOpenChange={setOpen}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/60 data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0" />
        <DialogPrimitive.Content
          className="fixed left-[50%] top-[20%] z-50 w-full max-w-lg translate-x-[-50%] rounded-xl border border-dark-border bg-dark-surface shadow-2xl data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:zoom-out-95 data-[state=open]:zoom-in-95"
          style={{ maxWidth: '90vw' }}
          onKeyDown={handleKeyDown}
          aria-label="Command palette"
        >
          <DialogPrimitive.Title className="sr-only">Command Palette</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">
            Search for symbols, strategies, pages, or actions
          </DialogPrimitive.Description>

          {/* Search input */}
          <div className="flex items-center gap-3 border-b border-dark-border px-4 py-3">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <input
              ref={inputRef}
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search symbols, strategies, pages, actions…"
              className="flex-1 bg-transparent text-sm text-gray-100 placeholder:text-muted-foreground outline-none font-mono"
              autoFocus
            />
            <kbd className="hidden sm:inline-flex items-center gap-1 rounded border border-dark-border bg-dark-bg px-1.5 py-0.5 text-xs text-muted-foreground font-mono">
              ESC
            </kbd>
          </div>

          {/* Results */}
          <div ref={listRef} className="max-h-[320px] overflow-y-auto py-2">
            {sections.length === 0 && query.trim() && (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                No results for "{query}"
              </div>
            )}

            {sections.length === 0 && !query.trim() && (
              <div className="px-4 py-8 text-center text-sm text-muted-foreground">
                <div className="flex items-center justify-center gap-2 mb-2">
                  <Command className="h-4 w-4" />
                  <span>Type to search</span>
                </div>
                <span className="text-xs">Navigate to symbols, strategies, pages, or trigger actions</span>
              </div>
            )}

            {sections.map((section) => (
              <div key={section.label}>
                <div className="px-4 py-1.5 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
                  {section.label === 'Recent' && <Clock className="inline h-3 w-3 mr-1 -mt-0.5" />}
                  {section.label}
                </div>
                {section.items.map((item) => {
                  const idx = flatIndex++;
                  const isSelected = idx === selectedIndex;
                  return (
                    <button
                      key={item.id}
                      data-index={idx}
                      type="button"
                      onClick={() => executeItem(item)}
                      onMouseEnter={() => setSelectedIndex(idx)}
                      className={cn(
                        'w-full flex items-center gap-3 px-4 py-2 text-left text-sm transition-colors',
                        isSelected
                          ? 'bg-accent-green/10 text-gray-100'
                          : 'text-gray-300 hover:bg-dark-bg',
                      )}
                    >
                      <span className="text-base shrink-0 w-5 text-center">{item.icon || '•'}</span>
                      <div className="flex-1 min-w-0">
                        <span className="font-mono font-medium truncate block">{item.label}</span>
                        {item.description && (
                          <span className="text-xs text-muted-foreground truncate block">
                            {item.description}
                          </span>
                        )}
                      </div>
                      {isSelected && <ArrowRight className="h-3 w-3 text-accent-green shrink-0" />}
                    </button>
                  );
                })}
              </div>
            ))}
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between border-t border-dark-border px-4 py-2 text-xs text-muted-foreground">
            <div className="flex items-center gap-3">
              <span>
                <kbd className="rounded border border-dark-border bg-dark-bg px-1 py-0.5 font-mono">↑↓</kbd> navigate
              </span>
              <span>
                <kbd className="rounded border border-dark-border bg-dark-bg px-1 py-0.5 font-mono">↵</kbd> select
              </span>
              <span>
                <kbd className="rounded border border-dark-border bg-dark-bg px-1 py-0.5 font-mono">esc</kbd> close
              </span>
            </div>
          </div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
};
