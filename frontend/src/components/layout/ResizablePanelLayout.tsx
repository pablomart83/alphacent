import { type FC, type ReactNode } from 'react';
import { Panel, Group, Separator, useDefaultLayout } from 'react-resizable-panels';
import { useMediaQuery } from '../../hooks/useMediaQuery';
import { cn } from '../../lib/utils';

interface PanelConfig {
  /** Unique id for this panel */
  id: string;
  /** Default size as percentage (0-100) */
  defaultSize: number;
  /** Minimum size — string with unit (e.g. "250px") or percentage number */
  minSize?: number | string;
  /** Panel content */
  content: ReactNode;
}

interface ResizablePanelLayoutProps {
  /** Unique key for persisting layout sizes to localStorage */
  layoutId: string;
  /** Direction of the split */
  direction?: 'horizontal' | 'vertical';
  /** Panel configurations */
  panels: PanelConfig[];
  className?: string;
}

export const ResizablePanelLayout: FC<ResizablePanelLayoutProps> = ({
  layoutId,
  direction = 'horizontal',
  panels,
  className,
}) => {
  const isBelowBreakpoint = useMediaQuery('(max-width: 1023px)');

  const panelIds = panels.map(p => p.id);

  const { defaultLayout, onLayoutChanged } = useDefaultLayout({
    id: layoutId,
    panelIds,
    storage: localStorage,
  });

  // Single-column stacked layout below 1024px
  if (isBelowBreakpoint) {
    return (
      <div className={cn('flex flex-col gap-2 h-full overflow-auto', className)}>
        {panels.map(panel => (
          <div key={panel.id} className="min-h-0">
            {panel.content}
          </div>
        ))}
      </div>
    );
  }

  // Build default layout from panel configs if no persisted layout
  const computedDefaultLayout = defaultLayout ?? Object.fromEntries(
    panels.map(p => [p.id, p.defaultSize])
  );

  return (
    <Group
      orientation={direction}
      onLayoutChanged={onLayoutChanged}
      defaultLayout={computedDefaultLayout}
      className={cn('h-full', className)}
    >
      {panels.map((panel, idx) => (
        <PanelWithHandle
          key={panel.id}
          panel={panel}
          isLast={idx === panels.length - 1}
          direction={direction}
        />
      ))}
    </Group>
  );
};

const PanelWithHandle: FC<{
  panel: PanelConfig;
  isLast: boolean;
  direction: 'horizontal' | 'vertical';
}> = ({ panel, isLast, direction }) => {
  return (
    <>
      <Panel
        id={panel.id}
        minSize={panel.minSize ?? '250px'}
        className="min-h-0 min-w-0"
      >
        {panel.content}
      </Panel>
      {!isLast && (
        <Separator
          className={cn(
            'group relative transition-colors',
            direction === 'horizontal'
              ? 'w-1 hover:w-1.5 bg-gray-800 hover:bg-gray-600 cursor-col-resize'
              : 'h-1 hover:h-1.5 bg-gray-800 hover:bg-gray-600 cursor-row-resize'
          )}
        />
      )}
    </>
  );
};
