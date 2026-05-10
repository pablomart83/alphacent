import { type FC } from 'react';
// import { useWebSocketConnection } from '../hooks/useWebSocket';

/**
 * WebSocket Connection Status Indicator
 * Shows connection state with color-coded indicator
 * Currently disabled - returns null to hide the indicator
 */
export const WebSocketIndicator: FC = () => {
  // WebSocket indicator temporarily disabled
  return null;
  
  /* Uncomment to re-enable WebSocket indicator
  const isConnected = useWebSocketConnection();

  return (
    <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-dark-surface border border-dark-border">
      <div className="relative">
        <div
          className={`w-2 h-2 rounded-full transition-colors ${
            isConnected ? 'bg-accent-green' : 'bg-accent-red'
          }`}
        />
        {isConnected && (
          <div className="absolute inset-0 w-2 h-2 rounded-full bg-accent-green animate-ping opacity-75" />
        )}
      </div>
      <span className="text-xs font-mono text-gray-400">
        {isConnected ? 'Live' : 'Disconnected'}
      </span>
    </div>
  );
  */
};
