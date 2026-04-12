import { type FC, type ReactNode, useState, useEffect } from 'react';
import { ChevronDown, ChevronRight, RefreshCw, X } from 'lucide-react';
import { cn } from '../../lib/utils';

interface PanelHeaderProps {
  title: string;
  /** Unique key for persisting collapse state to localStorage */
  panelId?: string;
  onRefresh?: () => void;
  onClose?: () => void;
  /** Extra action icons to render before the built-in ones */
  actions?: ReactNode;
  /** Controlled collapsed state (overrides internal state) */
  collapsed?: boolean;
  onCollapsedChange?: (collapsed: boolean) => void;
  className?: string;
  children?: ReactNode;
}

const STORAGE_PREFIX = 'alphacent_panel_collapsed_';

export const PanelHeader: FC<PanelHeaderProps> = ({
  title,
  panelId,
  onRefresh,
  onClose,
  actions,
  collapsed: controlledCollapsed,
  onCollapsedChange,
  className,
  children,
}) => {
  const storageKey = panelId ? `${STORAGE_PREFIX}${panelId}` : null;

  const [internalCollapsed, setInternalCollapsed] = useState(() => {
    if (controlledCollapsed !== undefined) return controlledCollapsed;
    if (storageKey) {
      return localStorage.getItem(storageKey) === 'true';
    }
    return false;
  });

  const isCollapsed = controlledCollapsed !== undefined ? controlledCollapsed : internalCollapsed;

  useEffect(() => {
    if (controlledCollapsed !== undefined) {
      setInternalCollapsed(controlledCollapsed);
    }
  }, [controlledCollapsed]);

  const toggleCollapse = () => {
    const next = !isCollapsed;
    setInternalCollapsed(next);
    if (storageKey) localStorage.setItem(storageKey, String(next));
    onCollapsedChange?.(next);
  };

  return (
    <div>
      <div
        className={cn(
          'flex items-center justify-between px-3 py-1.5 min-h-[32px]',
          'bg-[var(--color-dark-bg)] border-b border-[var(--color-dark-border)]',
          className
        )}
      >
        <div className="flex items-center gap-2 min-w-0">
          <button
            onClick={toggleCollapse}
            className="p-0.5 rounded text-gray-500 hover:text-gray-300 transition-colors shrink-0"
            aria-label={isCollapsed ? 'Expand panel' : 'Collapse panel'}
          >
            {isCollapsed ? <ChevronRight size={14} /> : <ChevronDown size={14} />}
          </button>
          <h3 className="text-xs font-semibold text-gray-300 truncate">{title}</h3>
        </div>

        <div className="flex items-center gap-1 shrink-0">
          {actions}
          {onRefresh && (
            <button
              onClick={onRefresh}
              className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
              title="Refresh"
            >
              <RefreshCw size={12} />
            </button>
          )}
          {onClose && (
            <button
              onClick={onClose}
              className="p-1 rounded text-gray-500 hover:text-gray-300 hover:bg-gray-800 transition-colors"
              title="Close"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Panel body — hidden when collapsed */}
      {!isCollapsed && children}
    </div>
  );
};
