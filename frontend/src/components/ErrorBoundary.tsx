import { Component, type ErrorInfo, type ReactNode } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'
import { Button } from '@/components/primitives'

interface ErrorBoundaryProps {
  children: ReactNode
  fallback?: (error: Error, reset: () => void) => ReactNode
}

interface ErrorBoundaryState {
  error: Error | null
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info)
  }

  reset = () => this.setState({ error: null })

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback(this.state.error, this.reset)
      return (
        <div className="flex h-screen items-center justify-center bg-[var(--bg-0)] p-6">
          <div className="max-w-[520px] w-full rounded-[4px] border border-[var(--status-error)]/40 bg-[var(--status-error-bg)] p-5">
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className="h-5 w-5 text-[var(--status-error)]" />
              <h2 className="text-[14px] font-semibold text-[var(--text-0)]">
                Something broke
              </h2>
            </div>
            <p className="text-[12px] text-[var(--text-1)] mb-3">{this.state.error.message}</p>
            <pre className="text-[10px] text-[var(--text-3)] bg-[var(--bg-0)] rounded-[2px] p-2 overflow-auto max-h-[200px] mb-3">
              {this.state.error.stack}
            </pre>
            <Button variant="primary" size="sm" onClick={this.reset}>
              <RefreshCw className="h-3.5 w-3.5" /> Try again
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
