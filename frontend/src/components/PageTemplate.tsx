import { type FC, type ReactNode } from 'react';
import { BottomWidgetZone } from './BottomWidgetZone';
import { cn } from '../lib/utils';

interface PageTemplateProps {
  /** Page title displayed in the header zone */
  title: string;
  /** Optional description below the title */
  description?: string;
  /** Action buttons rendered on the right side of the header */
  actions?: ReactNode;
  /** Main page content */
  children: ReactNode;
  /** Whether to show the bottom widget zone (default: true) */
  showWidgets?: boolean;
  className?: string;
}

export const PageTemplate: FC<PageTemplateProps> = ({
  title,
  description,
  actions,
  children,
  showWidgets = true,
  className,
}) => {
  return (
    <div className={cn('flex flex-col h-full overflow-hidden', className)}>
      {/* Header zone — 64px */}
      <div className="flex items-center justify-between px-4 md:px-6 h-16 min-h-[64px] max-h-[64px] shrink-0 border-b border-[var(--color-dark-border)]">
        <div className="min-w-0">
          <h1 className="text-xl font-bold text-gray-100 truncate">{title}</h1>
          {description && (
            <p className="text-xs text-gray-500 truncate mt-0.5">{description}</p>
          )}
        </div>
        {actions && (
          <div className="flex items-center gap-2 shrink-0 ml-4">
            {actions}
          </div>
        )}
      </div>

      {/* Main content zone — fills remaining */}
      <div className="flex-1 overflow-auto min-h-0">
        {children}
      </div>

      {/* Bottom widget zone */}
      {showWidgets && <BottomWidgetZone />}
    </div>
  );
};
