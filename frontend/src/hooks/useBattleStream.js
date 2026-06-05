import { useState, useEffect, useRef, useCallback } from 'react'

export function useBattleStream() {
  const [events, setEvents]         = useState([])
  const [isConnected, setConnected] = useState(false)
  const [p1State, setP1State]       = useState(null)   // state from p1's perspective
  const [p2State, setP2State]       = useState(null)   // state from p2's perspective
  const [battleInfo, setBattleInfo] = useState(null)   // from battle_start event
  const [battleResult, setBattleResult] = useState(null)
  const [thinking, setThinking]     = useState(null)   // 'p1' | 'p2' | null
  const wsRef       = useRef(null)
  const shouldConnect = useRef(false)
  const retryDelay  = useRef(1000)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return
    shouldConnect.current = true

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/ws/battles`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryDelay.current = 1000  // reset backoff on successful connection
    }

    ws.onclose = () => {
      setConnected(false)
      if (shouldConnect.current) {
        // Exponential backoff: 1s → 2s → 4s → max 30s
        const delay = Math.min(retryDelay.current, 30000)
        retryDelay.current = Math.min(retryDelay.current * 2, 30000)
        setTimeout(connect, delay)
      }
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)

        // Keepalive pings — ignore silently
        if (event.type === 'ping') return

        // Thinking indicator — don't add to event log
        if (event.type === 'thinking') {
          setThinking(event.player_role)
          return
        }

        setEvents(prev => [...prev, event])

        if (event.type === 'battle_start') {
          setBattleInfo(event)
          setBattleResult(null)
          setP1State(null)
          setP2State(null)
          setThinking(null)
        }

        if (event.type === 'turn') {
          setThinking(null)  // thinking resolved — model chose an action
          if (event.player_role === 'p1') setP1State(event)
          if (event.player_role === 'p2') setP2State(event)
        }

        if (event.type === 'battle_end') {
          setBattleResult(event)
          setThinking(null)
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
    setThinking(null)
  }, [])

  // Auto-connect on mount
  useEffect(() => {
    connect()
    return disconnect
  }, [connect, disconnect])

  return { events, isConnected, p1State, p2State, battleInfo, battleResult, thinking, reset }
}
