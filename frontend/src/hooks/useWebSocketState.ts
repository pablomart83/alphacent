import { useEffect, useState } from 'react'
import { wsManager, type ConnectionState } from '@/services/websocket'

interface WsStateInfo {
  state: ConnectionState
  attempt: number
  lastMessageAt: number | null
}

export function useWebSocketState(): WsStateInfo {
  const [info, setInfo] = useState<WsStateInfo>({
    state: wsManager.getState(),
    attempt: wsManager.getReconnectAttempts(),
    lastMessageAt: wsManager.getLastMessageAt(),
  })

  useEffect(() => {
    return wsManager.onStateChange((state, extra) => {
      setInfo({ state, attempt: extra.attempt, lastMessageAt: extra.lastMessageAt })
    })
  }, [])

  return info
}
