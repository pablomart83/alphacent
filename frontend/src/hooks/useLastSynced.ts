import { useState, useEffect, useCallback, useRef } from 'react';
import { wsManager } from '../services/websocket';

/**
 * Hook that tracks when data was last fetched/synced and displays
 * a human-readable "Last synced: X min ago" string.
 *
 * Updates every 30 seconds so the displayed time stays fresh.
 * Automatically bumps the timestamp when relevant WebSocket events arrive.
 */
export function useLastSynced(wsEventTypes?: string[]) {
  const [lastSyncedAt, setLastSyncedAt] = useState<Date | null>(null);
  const [label, setLabel] = useState<string>('Never synced');
  const intervalRef = useRef<number | null>(null);

  const touch = useCallback(() => {
    setLastSyncedAt(new Date());
  }, []);

  // Subscribe to WebSocket events that indicate fresh data
  useEffect(() => {
    const defaultEvents = [
      'position_update',
      'order_update',
      'strategy_update',
      'system_state',
      'autonomous_status',
      'market_data',
    ];
    const events = wsEventTypes ?? defaultEvents;
    const unsubs = events.map((evt) => wsManager.on(evt, () => touch()));
    return () => unsubs.forEach((u) => u());
  }, [wsEventTypes, touch]);

  // Recompute the label every 30s
  useEffect(() => {
    const compute = () => {
      if (!lastSyncedAt) {
        setLabel('Never synced');
        return;
      }
      const diffMs = Date.now() - lastSyncedAt.getTime();
      const diffSec = Math.floor(diffMs / 1000);
      if (diffSec < 10) {
        setLabel('Just now');
      } else if (diffSec < 60) {
        setLabel(`${diffSec}s ago`);
      } else {
        const mins = Math.floor(diffSec / 60);
        setLabel(mins === 1 ? '1 min ago' : `${mins} min ago`);
      }
    };

    compute();
    intervalRef.current = window.setInterval(compute, 30_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [lastSyncedAt]);

  return { lastSyncedAt, label, touch };
}
