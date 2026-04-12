import { type FC, useEffect, useRef, memo } from 'react';
import { Terminal } from 'lucide-react';
import { cn } from '../lib/utils';

interface LogEntry {
  timestamp: string;
  level: 'INFO' | 'WARNING' | 'ERROR' | 'SUCCESS' | 'DEBUG';
  message: string;
}

interface InlineTerminalProps {
  logs: LogEntry[];
}

export const InlineTerminal: FC<InlineTerminalProps> = memo(({ logs }) => {
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom when new logs arrive
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs.length]); // Only trigger on length change, not full array

  if (logs.length === 0) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground">
        <div className="text-center">
          <Terminal className="h-12 w-12 mx-auto mb-2 opacity-50" />
          <p className="text-sm">Waiting for cycle execution...</p>
          <p className="text-xs mt-1">Trigger a cycle to see real-time logs</p>
        </div>
      </div>
    );
  }

  return (
    <div
      ref={scrollRef}
      className="h-[300px] overflow-y-auto bg-gray-950 font-mono text-xs p-4 rounded-lg border border-border"
      style={{
        scrollbarWidth: 'thin',
        scrollbarColor: '#374151 #1f2937',
      }}
    >
      {logs.map((log, index) => (
        <div
          key={`${index}-${log.timestamp}`}
          className="flex items-start gap-2 py-0.5"
        >
          <span className="text-gray-600 flex-shrink-0 select-none text-xs w-16">
            {log.timestamp}
          </span>
          <span
            className={cn(
              'flex-shrink-0 select-none w-3',
              log.level === 'INFO' ? 'text-blue-400' :
              log.level === 'SUCCESS' ? 'text-accent-green' :
              log.level === 'WARNING' ? 'text-yellow-400' :
              log.level === 'ERROR' ? 'text-accent-red' :
              'text-gray-500'
            )}
          >
            {log.level === 'INFO' ? 'ℹ' :
             log.level === 'SUCCESS' ? '✓' :
             log.level === 'WARNING' ? '⚠' :
             log.level === 'ERROR' ? '✗' :
             '◆'}
          </span>
          <span
            className={cn(
              'flex-shrink-0 font-semibold w-12 select-none text-xs',
              log.level === 'INFO' ? 'text-blue-400' :
              log.level === 'SUCCESS' ? 'text-accent-green' :
              log.level === 'WARNING' ? 'text-yellow-400' :
              log.level === 'ERROR' ? 'text-accent-red' :
              'text-gray-500'
            )}
          >
            {log.level}
          </span>
          <span className="text-gray-300 break-all leading-tight flex-1">{log.message}</span>
        </div>
      ))}
    </div>
  );
});

InlineTerminal.displayName = 'InlineTerminal';
