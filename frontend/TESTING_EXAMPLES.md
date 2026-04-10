# Testing Examples for Loading and Error States

## Setup

To run these tests, first install the testing dependencies:

```bash
npm install --save-dev vitest @testing-library/react @testing-library/jest-dom
```

## Example Tests

```typescript
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LoadingSpinner, LoadingOverlay } from './components/LoadingSpinner';
import { ErrorMessage } from './components/ErrorMessage';
import { Skeleton, SkeletonTable, SkeletonCard } from './components/SkeletonLoader';
import { ServiceUnavailable, DegradedMode } from './components/ServiceUnavailable';

describe('LoadingSpinner', () => {
  it('renders spinner with correct size', () => {
    const { container } = render(<LoadingSpinner size="md" />);
    const spinner = container.querySelector('[role="status"]');
    expect(spinner).toBeInTheDocument();
    expect(spinner).toHaveClass('w-8', 'h-8');
  });

  it('renders loading overlay with message', () => {
    render(<LoadingOverlay message="Loading data..." />);
    expect(screen.getByText('Loading data...')).toBeInTheDocument();
  });
});

describe('ErrorMessage', () => {
  it('renders error message', () => {
    render(<ErrorMessage message="Test error" />);
    expect(screen.getByText('Test error')).toBeInTheDocument();
  });

  it('shows retry button when retryable', () => {
    const onRetry = vi.fn();
    render(<ErrorMessage message="Test error" onRetry={onRetry} retryable={true} />);
    
    const retryButton = screen.getByText('↻ Retry');
    expect(retryButton).toBeInTheDocument();
  });

  it('calls onRetry when retry button clicked', async () => {
    const onRetry = vi.fn().mockResolvedValue(undefined);
    render(<ErrorMessage message="Test error" onRetry={onRetry} retryable={true} />);
    
    const retryButton = screen.getByText('↻ Retry');
    fireEvent.click(retryButton);
    
    await waitFor(() => {
      expect(onRetry).toHaveBeenCalledTimes(1);
    });
  });

  it('does not show retry button when not retryable', () => {
    render(<ErrorMessage message="Test error" retryable={false} />);
    expect(screen.queryByText('↻ Retry')).not.toBeInTheDocument();
  });
});

describe('Skeleton Loaders', () => {
  it('renders basic skeleton', () => {
    const { container } = render(<Skeleton className="h-4 w-20" />);
    const skeleton = container.querySelector('.animate-pulse');
    expect(skeleton).toBeInTheDocument();
  });

  it('renders skeleton table with correct rows and columns', () => {
    const { container } = render(<SkeletonTable rows={3} columns={5} />);
    const rows = container.querySelectorAll('tbody tr');
    expect(rows).toHaveLength(3);
    
    const firstRowCells = rows[0].querySelectorAll('td');
    expect(firstRowCells).toHaveLength(5);
  });

  it('renders skeleton card', () => {
    const { container } = render(<SkeletonCard />);
    const card = container.querySelector('.bg-dark-bg');
    expect(card).toBeInTheDocument();
  });
});

describe('ServiceUnavailable', () => {
  it('renders service unavailable message', () => {
    render(
      <ServiceUnavailable
        serviceName="Test Service"
        message="Service is down"
        impact="Feature disabled"
      />
    );
    
    expect(screen.getByText('Test Service Unavailable')).toBeInTheDocument();
    expect(screen.getByText('Service is down')).toBeInTheDocument();
    expect(screen.getByText(/Feature disabled/)).toBeInTheDocument();
  });

  it('shows retry button when onRetry provided', () => {
    const onRetry = vi.fn();
    render(
      <ServiceUnavailable
        serviceName="Test Service"
        onRetry={onRetry}
      />
    );
    
    expect(screen.getByText('↻ Retry Connection')).toBeInTheDocument();
  });
});

describe('DegradedMode', () => {
  it('renders degraded mode message with features', () => {
    const features = ['Feature 1 disabled', 'Feature 2 limited'];
    render(
      <DegradedMode
        features={features}
        reason="Service unavailable"
      />
    );
    
    expect(screen.getByText('Running in Degraded Mode')).toBeInTheDocument();
    expect(screen.getByText('Service unavailable')).toBeInTheDocument();
    expect(screen.getByText('Feature 1 disabled')).toBeInTheDocument();
    expect(screen.getByText('Feature 2 limited')).toBeInTheDocument();
  });
});
```

## Running Tests

After installing dependencies, run tests with:

```bash
npm test
```

Or for watch mode:

```bash
npm test -- --watch
```
