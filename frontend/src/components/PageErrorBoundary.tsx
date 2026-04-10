import { type FC, type ReactNode } from 'react';
import { ErrorBoundary } from './ErrorMessage';
import { Button } from './ui/Button';

interface PageErrorBoundaryProps {
  pageName: string;
  children: ReactNode;
}

/**
 * Per-page error boundary that shows a page-specific fallback with a "Reload Page" button.
 * Wraps the existing ErrorBoundary class component so the sidebar/header remain functional.
 */
export const PageErrorBoundary: FC<PageErrorBoundaryProps> = ({ pageName, children }) => {
  return (
    <ErrorBoundary
      fallback={(error, reset) => (
        <div className="flex flex-col items-center justify-center min-h-[50vh] p-8 text-center">
          <div className="bg-dark-surface border border-dark-border rounded-lg p-8 max-w-md w-full">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-lg font-semibold text-white mb-2">
              {pageName} encountered an error
            </h2>
            <p className="text-sm text-gray-400 mb-6 font-mono">
              {error.message}
            </p>
            <div className="flex gap-3 justify-center">
              <Button variant="outline" onClick={reset}>
                Try Again
              </Button>
              <Button onClick={() => window.location.reload()}>
                Reload Page
              </Button>
            </div>
          </div>
        </div>
      )}
    >
      {children}
    </ErrorBoundary>
  );
};
