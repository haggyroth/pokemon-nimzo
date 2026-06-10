/**
 * ShowdownBattleScene — OP-02 (#84) Stage 3: live renderer.
 *
 * Connects to the spectator-proxy socket `/ws/showdown/{room}` and feeds the
 * raw Showdown protocol stream to the PS `Battle` class loaded via
 * `useShowdownBundle`.
 *
 * Design notes
 * ------------
 * Single effect on [room, bundleReady]: the Battle instance is created first,
 * then the WebSocket opens. This eliminates any need for a line buffer because
 * the Showdown server replays the full battle log from the start when a
 * spectator joins a room — arriving "late" is safe.
 *
 * `battle.add(line)` is the public API for feeding protocol lines.
 * `battle.play()` keeps the animation loop running; calling it after each
 * batch is idempotent if already playing.
 *
 * The status overlay is display-only; the renderer itself drives the visual.
 */

import { useEffect, useRef, useState } from 'react'
import { useShowdownBundle } from '../hooks/useShowdownBundle'

/** Strip the room-prefix line and proxy keepalive; return bare |...| lines. */
function protocolLinesFromFrame(frame) {
  return frame
    .split('\n')
    .filter(line => line && !line.startsWith('>') && line !== '|ping')
}

export default function ShowdownBattleScene({ room }) {
  const { ready: bundleReady, error: bundleError } = useShowdownBundle()
  const frameRef  = useRef(null)
  const logRef    = useRef(null)
  const battleRef = useRef(null)
  const wsRef     = useRef(null)
  const [status, setStatus] = useState('loading')   // loading|connecting|live|ended|error

  useEffect(() => {
    if (!room || !bundleReady || !frameRef.current || !logRef.current) return

    // Destroy any previous instance for this room slot.
    battleRef.current?.destroy?.()
    battleRef.current = null

    let battle
    try {
      battle = new window.Battle({
        $frame:    window.jQuery(frameRef.current),
        $logFrame: window.jQuery(logRef.current),
        id: room,
        subscription: (s) => {
          if (s === 'ended') setStatus('ended')
          else if (s === 'playing' || s === 'turn') setStatus('live')
        },
      })
      battleRef.current = battle
    } catch {
      queueMicrotask(() => setStatus('error'))
      return
    }

    // Open the proxy socket after the Battle instance exists so every
    // replayed line (full log from the start) lands immediately.
    queueMicrotask(() => setStatus('connecting'))

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/showdown/${room}`)
    wsRef.current = ws

    ws.onopen = () => setStatus('live')

    ws.onmessage = (e) => {
      const lines = protocolLinesFromFrame(e.data)
      if (lines.length === 0) return
      for (const line of lines) battle.add(line)
      // play() is idempotent — safe to call on every message batch.
      battle.play()
    }

    ws.onerror = () => setStatus('error')
    ws.onclose = () => setStatus(prev => (prev === 'error' ? 'error' : 'ended'))

    return () => {
      ws.close()
      wsRef.current = null
      battle?.destroy?.()
      battleRef.current = null
    }
  }, [room, bundleReady])

  // ── Placeholder states ────────────────────────────────────────────────────

  if (bundleError) {
    return (
      <div className="sbs-placeholder sbs-placeholder--error">
        Showdown renderer unavailable: {bundleError.message}
      </div>
    )
  }

  if (!room || !bundleReady) {
    return (
      <div className="sbs-placeholder">
        {!bundleReady ? 'Loading Showdown renderer…' : 'Waiting for battle room…'}
      </div>
    )
  }

  // ── Live scene ───────────────────────────────────────────────────────────

  const statusLabel = status === 'live' ? '● LIVE'
    : status === 'ended' ? 'ENDED'
    : status === 'error' ? 'ERROR'
    : 'CONNECTING'

  // Cockpit layout: a header strip, the centered PS stage, and the log panel.
  // The header and the space around the stage are the slots Phase 2 fills with
  // labels, heuristics, and win-probability — data lives *around* the frame, not
  // overlaid on it.
  return (
    <div className="showdown-battle-scene sbs-cockpit">
      <div className="sbs-cockpit-header">
        <span className={`sbs-status-chip sbs-status-chip--${status}`}>{statusLabel}</span>
      </div>

      <div className="sbs-stage">
        {/* PS Battle class draws the animated scene into this div. */}
        <div ref={frameRef} className="sbs-frame" />

        {/* Overlay: only visible when not yet live or after the battle ends. */}
        {status !== 'live' && (
          <div className={`sbs-status-overlay sbs-status-overlay--${status}`}>
            {status === 'connecting' && 'Connecting to battle room…'}
            {status === 'ended'      && 'Battle ended.'}
            {status === 'error'      && 'Connection error — try refreshing.'}
          </div>
        )}
      </div>

      <div ref={logRef} className="sbs-log" />
    </div>
  )
}
