import { useEffect, useCallback, useState } from 'react';
import { useNavigate } from 'react-router-dom';

/** Route map for number key navigation (1-8) */
const PAGE_ROUTES: Record<string, string> = {
  '1': '/',
  '2': '/portfolio',
  '3': '/orders',
  '4': '/strategies',
  '5': '/autonomous',
  '6': '/risk',
  '7': '/analytics',
  '8': '/settings',
};

export interface KeyboardShortcutDef {
  key: string;
  label: string;
  description: string;
  category: 'navigation' | 'actions' | 'general';
}

/** All registered shortcuts for display in help overlay / settings */
export const KEYBOARD_SHORTCUTS: KeyboardShortcutDef[] = [
  { key: '1-8', label: '1–8', description: 'Navigate to sidebar pages', category: 'navigation' },
  { key: 'r', label: 'R', description: 'Refresh current page data', category: 'actions' },
  { key: 'Escape', label: 'Esc', description: 'Close open modal / dialog', category: 'general' },
  { key: 'mod+k', label: '⌘/Ctrl + K', description: 'Command palette', category: 'actions' },
  { key: '?', label: '?', description: 'Show keyboard shortcuts help', category: 'general' },
];

interface UseKeyboardShortcutsOptions {
  /** Callback fired when user presses R (refresh) */
  onRefresh?: () => void;
  /** Whether shortcuts are enabled (default true) */
  enabled?: boolean;
}

/**
 * Returns `showHelp` state + setter so the layout can render the overlay.
 */
export function useKeyboardShortcuts(options: UseKeyboardShortcutsOptions = {}) {
  const { onRefresh, enabled = true } = options;
  const navigate = useNavigate();
  const [showHelp, setShowHelp] = useState(false);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (!enabled) return;

      // Skip when user is typing in an input / textarea / contenteditable
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if ((e.target as HTMLElement)?.isContentEditable) return;

      const isMod = e.metaKey || e.ctrlKey;

      // Ctrl/Cmd + K — handled by CommandPalette component directly
      if (isMod && e.key.toLowerCase() === 'k') {
        return;
      }

      // Don't process single-key shortcuts when modifier keys are held
      if (isMod || e.altKey) return;

      // Escape — close modals (also close help overlay)
      if (e.key === 'Escape') {
        if (showHelp) {
          setShowHelp(false);
          return;
        }
        // Dispatch a custom event that modals can listen to
        document.dispatchEvent(new CustomEvent('keyboard-escape'));
        return;
      }

      // ? — toggle help overlay
      if (e.key === '?') {
        setShowHelp((prev) => !prev);
        return;
      }

      // R — refresh
      if (e.key.toLowerCase() === 'r') {
        onRefresh?.();
        return;
      }

      // 1-8 — page navigation
      if (PAGE_ROUTES[e.key]) {
        navigate(PAGE_ROUTES[e.key]);
        return;
      }
    },
    [enabled, navigate, onRefresh, showHelp],
  );

  useEffect(() => {
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return { showHelp, setShowHelp };
}
