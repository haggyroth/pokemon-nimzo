import { useState, useEffect, useRef, useCallback } from 'react'

// Keep only the most recent N events to prevent unbounded memory growth
// over long tournaments.
const MAX_EVENTS = 500

export function useBattleStream() {
  const [events, setEvents]             = useState([])
  const [isConnected, setConnected]     = useState(false)
  const [p1State, setP1State]           = useState(null)
  const [p2State, setP2State]           = useState(null)
  const [battleInfo, setBattleInfo]     = useState(null)
  const [battleResult, setBattleResult] = useState(null)
  const [thinking, setThinking]         = useState(null)   // 'p1' | 'p2' | null
  const [tournament, setTournament]     = useState(null)   // tournament progress state
  const [draft, setDraft]               = useState(null)   // draft phase state
  const wsRef         = useRef(null)
  const shouldConnect = useRef(false)
  const retryDelay    = useRef(1000)
  // Stable ref so the ws.onclose handler can schedule a reconnect without
  // capturing `connect` in a closure before it's declared (immutability rule).
  const connectRef    = useRef(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN ||
        wsRef.current?.readyState === WebSocket.CONNECTING) return
    shouldConnect.current = true

    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${protocol}://${location.host}/ws/battles`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      retryDelay.current = 1000
    }

    ws.onclose = () => {
      setConnected(false)
      if (shouldConnect.current) {
        const delay = Math.min(retryDelay.current, 30000)
        retryDelay.current = Math.min(retryDelay.current * 2, 30000)
        setTimeout(() => connectRef.current?.(), delay)
      }
    }

    ws.onerror = () => ws.close()

    ws.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data)

        if (event.type === 'ping') return

        // Draft phase events
        if (event.type === 'draft_start') {
          setDraft(prev => ({
            ...(prev || { p1: { picks: [], done: false }, p2: { picks: [], done: false } }),
            tier: event.tier,
            battleId: event.battle_id,
            [event.player_role]: { picks: [], done: false },
          }))
          return
        }

        if (event.type === 'draft_pick') {
          setDraft(prev => {
            if (!prev) return prev
            const role = event.player_role
            const existing = prev[role] || { picks: [], done: false }
            return {
              ...prev,
              [role]: {
                ...existing,
                picks: [...existing.picks, { species: event.species, types: event.types }],
              },
            }
          })
          return
        }

        if (event.type === 'draft_complete') {
          setDraft(prev => {
            if (!prev) return prev
            const role = event.player_role
            return {
              ...prev,
              [role]: { picks: event.team, done: true },
            }
          })
          return
        }

        if (event.type === 'thinking') {
          setThinking(event.player_role)
          return
        }

        // Tournament lifecycle events — update progress, don't pollute battle log
        if (event.type === 'tournament_start') {
          setTournament({
            id: event.tournament_id,
            players: event.players,
            total: event.total_battles,
            rounds: event.rounds,
            tier: event.tier ?? 'random',
            done: 0,
            status: 'running',
            leaderboard: null,
          })
          return
        }

        if (event.type === 'tournament_progress') {
          setTournament(prev => prev ? {
            ...prev,
            battleNum: event.battle_num,
            currentBattleId: event.battle_id,
            p1: event.p1,
            p2: event.p2,
          } : null)
          return
        }

        if (event.type === 'tournament_standings') {
          setTournament(prev => prev ? {
            ...prev,
            standings: event.standings,
          } : null)
          return
        }

        if (event.type === 'tournament_end') {
          setTournament(prev => prev ? {
            ...prev,
            status: 'completed',
            done: prev.total,
            leaderboard: event.leaderboard,
          } : null)
          return
        }

        if (event.type === 'tournament_cancelled') {
          setTournament(prev => prev ? {
            ...prev,
            status: 'cancelled',
            done: event.battles_completed,
          } : null)
          return
        }

        setEvents(prev => {
          const next = [...prev, event]
          return next.length > MAX_EVENTS ? next.slice(-MAX_EVENTS) : next
        })

        if (event.type === 'battle_start') {
          setBattleInfo(event)
          setBattleResult(null)
          setP1State(null)
          setP2State(null)
          setThinking(null)
          setDraft(null)   // clear draft once battle proper begins
        }

        if (event.type === 'turn') {
          setThinking(null)
          if (event.player_role === 'p1') setP1State(event)
          if (event.player_role === 'p2') setP2State(event)
          // Increment tournament battle counter on each new turn 1
          if (event.turn === 1) {
            setTournament(prev => prev ? { ...prev, done: Math.max(0, (prev.done || 0)) } : null)
          }
        }

        if (event.type === 'battle_end') {
          setBattleResult(event)
          setThinking(null)
          setTournament(prev => prev ? { ...prev, done: (prev.done || 0) + 1 } : null)
        }

        if (event.type === 'battle_cancelled') {
          setBattleResult({ ...event, cancelled: true })
          setThinking(null)
        }
      } catch {
        // non-JSON WebSocket frames are silently ignored
      }
    }
  }, [])

  // Keep the ref current so ws.onclose can schedule a reconnect after
  // `connect` is fully initialised (must be in an effect, not render).
  useEffect(() => {
    connectRef.current = connect
  }, [connect])

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
    setDraft(null)
  }, [])

  const clearTournament = useCallback(() => setTournament(null), [])

  useEffect(() => {
    connect()
    return disconnect
  }, [connect, disconnect])

  return {
    events, isConnected, p1State, p2State, battleInfo, battleResult,
    thinking, tournament, draft, reset, clearTournament,
  }
}
