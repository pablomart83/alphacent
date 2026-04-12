import { type FC, type ReactNode } from 'react';
import { cn } from '../../lib/utils';

interface SectionLabelProps {
  /** Section title text */
  children: ReactNode;
  /** Optional right-aligned actions (filters, buttons) */
  actions?: ReactNode;
  /** Additional className */
  className?: string;
}

/**
 * Flat section label for tab interiors — replaces nested PanelHeaders.
 * Renders as a thin uppercase label with optional right-aligned actions.
 * 
 * Usage:
 * ```tsx
 * <SectionLabel>Risk Limits</SectionLabel>
 * <SectionLabel actions={<Select ... />}>Positions</SectionLabel>
 * ```
 */
export const SectionLabel: FC<SectionLabelProps> = ({ children, actions, className }) => (
  <div className={cn('flex items-center justify-between mb-1.5', className)}>
    <span className="text-xs font-medium text-gray-500 tracking-wide">
      {children}
    </span>
    {actions && (
      <div className="flex items-center gap-1.5">
        {actions}
      </div>
    )}
  </div>
);
