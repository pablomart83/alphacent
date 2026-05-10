import React, { type FC, useState } from 'react';

interface ErrorMessageProps {
  message: string;
  onRetry?: () => void | Promise<void>;
  retryable?: boolean;
  className?: string;
}

export const ErrorMessage: FC<ErrorMessageProps> = ({
  message,
  onRetry,
  retryable = true,
  className = '',
}) => {
  const [retrying, setRetrying] = useState(false);

  const handleRetry = async () => {
    if (!onRetry) return;

    setRetrying(true);
    try {
      await onRetry();
    } catch (err) {
      console.error('Retry failed:', err);
    } finally {
      setRetrying(false);
    }
  };

  return (
    <div
      className={`bg-accent-red/10 border border-accent-red/30 rounded-lg p-4 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 text-accent-red text-lg">⚠️</div>
        <div className="flex-1">
          <p className="text-accent-red text-sm font-mono">{message}</p>
          {retryable && onRetry && (
            <button
              onClick={handleRetry}
              disabled={retrying}
              className="mt-3 px-3 py-1 text-xs font-mono bg-accent-red/20 text-accent-red border border-accent-red/30 rounded hover:bg-accent-red/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {retrying ? 'Retrying...' : '↻ Retry'}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

interface ErrorBoundaryState {
  hasError: boolean;
  error: Error | null;
}

interface ErrorBoundaryProps {
  children: React.ReactNode;
  fallback?: (error: Error, reset: () => void) => React.ReactNode;
}

export class ErrorBoundary extends React.Component<ErrorBoundaryProps, ErrorBoundaryState> {
  constructor(props: ErrorBoundaryProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('ErrorBoundary caught an error:', error, errorInfo);
  }

  reset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError && this.state.error) {
      if (this.props.fallback) {
        return this.props.fallback(this.state.error, this.reset);
      }

      return (
        <div className="bg-dark-surface border border-dark-border rounded-lg p-6">
          <ErrorMessage
            message={`Component error: ${this.state.error.message}`}
            onRetry={this.reset}
            retryable={true}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
