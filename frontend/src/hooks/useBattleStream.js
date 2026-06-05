import { useState, useEffect, useRef, useCallback } from 'react'

export function useBattleStream() {
  const [events, setEvents]       = useState([])
  const [isConnected, setConnected] = useState(false)
  const [p1State, setP1State]     = useState(null)   // state from p1's perspective
  const [p2State, setP2State]     = useState(null)   // state from p2's perspective
  const [battleInfo, setBattleInfo] = useState(null) // from battle_start event
  const [battleResult, setBattleResult] = useState(null)
  const wsRef = useRef(null)
  const shouldConnect = useRef(false)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return
    shouldConnect.current = true

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/ws/battles`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => {
      setConnected(false)
      // Auto-reconnect after 2s if we should still be connected
      if (shouldConnect.current) {
        setTimeout(connect, 2000)
      }
    }
    ws.onerror = () => ws.close()

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)
        setEvents(prev => [...prev, event])

        if (event.type === 'battle_start') {
          setBattleInfo(event)
          setBattleResult(null)
          setP1State(null)
          setP2State(null)
        }

        if (event.type === 'turn') {
          if (event.player_role === 'p1') setP1State(event)
          if (event.player_role === 'p2') setP2State(event)
        }

        if (event.type === 'battle_end') {
          setBattleResult(event)
        }
      } catch {}
    }
  }, [])

  const disconnect = useCallback(() => {
    shouldConnect.current = false
    wsRef.current?.close()
    wsRef.current = null
  }, [])

  const reset = useCallback(() => {
    setEvents([])
    setP1State(null)
    setP2State(null)
    setBattleInfo(null)
    setBattleResult(null)
  }, [])

  // Auto-connect on mount
  useEffect(() => {
    connect()
    return disconnect
  }, [connect, disconnect])

  return { events, isConnected, p1State, p2State, battleInfo, battleResult, reset }
}
