import { cn } from '@/lib/utils'
import { useTradingMode } from '@/stores'

interface AccountToggleProps {
  liveEnabled?: boolean
  size?: 'sm' | 'md'
}

export function AccountToggle({ liveEnabled = false, size = 'sm' }: AccountToggleProps) {
  const mode = useTradingMode((s) => s.mode)
  const setMode = useTradingMode((s) => s.setMode)

  const buttonBase = cn(
    'inline-flex items-center justify-center',
    'font-semibold uppercase tracking-wide',
    'border transition-colors outline-none',
    'focus-visible:outline-2 focus-visible:outline-[var(--border-focus)]',
    size === 'sm' ? 'h-6 px-2 text-[10px]' : 'h-7 px-3 text-[11px]',
  )

  return (
    <div
      role="radiogroup"
      aria-label="Trading mode"
      className="inline-flex rounded-[3px] overflow-hidden border border-[var(--border-default)]"
    >
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'DEMO'}
        onClick={() => setMode('DEMO')}
        className={cn(
          buttonBase,
          'border-transparent',
          mode === 'DEMO'
            ? 'bg-[color-mix(in_oklab,var(--account-demo)_18%,transparent)] text-[var(--account-demo)]'
            : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
        )}
      >
        Demo
      </button>
      <button
        type="button"
        role="radio"
        aria-checked={mode === 'LIVE'}
        onClick={() => setMode('LIVE')}
        className={cn(
          buttonBase,
          'border-l border-[var(--border-default)]',
          mode === 'LIVE' && liveEnabled
            ? 'bg-[color-mix(in_oklab,var(--account-live)_18%,transparent)] text-[var(--account-live)]'
            : mode === 'LIVE'
              ? 'bg-[var(--bg-hover)] text-[var(--text-2)]'
              : 'text-[var(--text-2)] hover:text-[var(--text-0)] hover:bg-[var(--bg-hover)]',
        )}
        title={!liveEnabled ? 'Live trading is currently disabled' : undefined}
      >
        <span
          className={cn(
            'inline-block h-1.5 w-1.5 rounded-full mr-1.5',
            liveEnabled ? 'bg-[var(--account-live)]' : 'bg-[var(--text-3)]',
          )}
          aria-hidden
        />
        Live
      </button>
    </div>
  )
}
