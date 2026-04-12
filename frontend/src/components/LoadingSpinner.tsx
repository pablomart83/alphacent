import { type FC } from 'react';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const LoadingSpinner: FC<LoadingSpinnerProps> = ({ size = 'md', className = '' }) => {
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-2',
    lg: 'w-12 h-12 border-3',
  };

  return (
    <div
      className={`${sizeClasses[size]} border-gray-600 border-t-accent-green rounded-full animate-spin ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
};

interface LoadingOverlayProps {
  message?: string;
}

export const LoadingOverlay: FC<LoadingOverlayProps> = ({ message = 'Loading...' }) => {
  return (
    <div className="flex flex-col items-center justify-center py-12 min-h-[200px]" style={{ backgroundColor: 'var(--color-dark-bg)' }}>
      <LoadingSpinner size="lg" />
      <p className="mt-4 text-gray-400 text-sm font-mono">{message}</p>
    </div>
  );
};
