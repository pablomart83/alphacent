import { PanelGroup, Panel, PanelResizeHandle } from 'react-resizable-panels'
import { useLayoutStore } from '@/stores'
import { cn } from '@/lib/utils'

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
}

export function ResizablePanelLayout({
  layoutId,
  direction = 'horizontal',
  panels,
  className,
}: ResizablePanelLayoutProps) {
  const persistedSizes = useLayoutStore((s) => s.panelSizes[layoutId])
  const setPanelSizes = useLayoutStore((s) => s.setPanelSizes)

  return (
    <PanelGroup
      direction={direction}
      onLayout={(sizes) => setPanelSizes(layoutId, sizes)}
      className={cn('h-full w-full', className)}
    >
      {panels.map((p, idx) => (
        <>
          <Panel
            key={p.id}
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
        </>
      ))}
    </PanelGroup>
  )
}
