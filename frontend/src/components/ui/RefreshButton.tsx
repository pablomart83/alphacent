import * as React from 'react';
import { RefreshCw } from 'lucide-react';
import { Button, type ButtonProps } from './Button';
import { cn } from '@/lib/utils';

export interface RefreshButtonProps extends Omit<ButtonProps, 'children'> {
  /** Whether the refresh action is currently in progress */
  loading?: boolean;
  /** Optional label text next to the icon */
  label?: string;
  /** Button size — defaults to 'sm' for compact card headers */
  size?: ButtonProps['size'];
  /** Called when the button is clicked */
  onClick?: () => void;
}

/**
 * Reusable refresh button with spinning icon during loading state.
 * Designed to be compact enough for card headers while remaining accessible.
 */
export const RefreshButton: React.FC<RefreshButtonProps> = ({
  loading = false,
  label,
  size = 'sm',
  onClick,
  className,
  variant = 'outline',
  ...props
}) => {
  return (
    <Button
      variant={variant}
      size={size}
      onClick={onClick}
      disabled={loading}
      className={cn('gap-2', className)}
      title={label || 'Refresh'}
      {...props}
    >
      <RefreshCw className={cn('h-4 w-4', loading && 'animate-spin')} />
      {label && <span>{loading ? 'Refreshing...' : label}</span>}
    </Button>
  );
};
