import { Fragment } from 'react'
import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'
import { useLayoutStore } from '@/stores'
import { cn } from '@/lib/utils'
import type { Breakpoint } from '@/lib/design-tokens'
import { useBreakpoint } from '@/hooks/useBreakpoint'

export interface PanelConfig {
  id: string
  defaultSize: number
  minSize?: number
  maxSize?: number
  content: React.ReactNode
}

interface ResizablePanelLayoutProps {
  layoutId: string
  direction?: 'horizontal' | 'vertical'
  panels: PanelConfig[]
  className?: string
  /**
   * Below this breakpoint the resizable panels collapse into a single scrolling
   * column (in declared order) — resize handles don't make sense on a phone.
   * Opt-in; unset preserves the original always-side-by-side behaviour.
   */
  stackBelow?: Breakpoint
}

export function ResizablePanelLayout({
  layoutId,
  direction = 'horizontal',
  panels,
  className,
  stackBelow,
}: ResizablePanelLayoutProps) {
  const persistedSizes = useLayoutStore((s) => s.panelSizes[layoutId])
  const setPanelSizes = useLayoutStore((s) => s.setPanelSizes)
  const { below } = useBreakpoint()

  if (stackBelow && below(stackBelow)) {
    return (
      <div className={cn('flex h-full w-full flex-col overflow-y-auto', className)}>
        {panels.map((p) => (
          <div key={p.id} className="min-h-0 w-full">
            {p.content}
          </div>
        ))}
      </div>
    )
  }

  return (
    <PanelGroup
      direction={direction}
      onLayout={(sizes) => setPanelSizes(layoutId, sizes)}
      className={cn('h-full w-full', className)}
    >
      {panels.map((p, idx) => (
        <Fragment key={p.id}>
          <Panel
            id={p.id}
            order={idx}
            defaultSize={persistedSizes?.[idx] ?? p.defaultSize}
            minSize={p.minSize}
            maxSize={p.maxSize}
            className="min-h-0 min-w-0"
          >
            {p.content}
          </Panel>
          {idx < panels.length - 1 && (
            <PanelResizeHandle
              className={cn(
                direction === 'horizontal'
                  ? 'w-px hover:w-[3px] bg-[var(--border-subtle)] hover:bg-[var(--accent-primary)]'
                  : 'h-px hover:h-[3px] bg-[var(--border-subtle)] hover:bg-[var(--accent-primary)]',
                'transition-colors',
              )}
            />
          )}
        </Fragment>
      ))}
    </PanelGroup>
  )
}
