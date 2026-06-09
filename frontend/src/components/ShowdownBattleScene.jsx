/**
 * ShowdownBattleScene — OP-02 (#84) SCAFFOLD.
 *
 * Renders an LLM battle using Pokémon Showdown's own animated battle scene by
 * (1) opening the spectator-proxy socket `/ws/showdown/{room}` exposed by
 * `src/nidozo/api/ws_showdown.py`, and (2) feeding the raw protocol stream to a
 * vendored copy of Showdown's `Battle` class.
 *
 * STATUS: scaffold only. The backend proxy (Stage 0) is implemented and tested.
 * This component documents the integration contract and wires the socket, but
 * the renderer itself is inert until the PS client battle bundle is vendored
 * (Stage 2 in docs/op-02-architecture.md). Until then, mounting this shows a
 * placeholder; the app should default to the existing <BattleField/> view.
 *
 * --- What remains (Stage 2/3) ---
 * 1. Vendor under frontend/vendor/showdown/ (all MIT, keep license headers):
 *      jquery, battle.js, battle-animations.js, battle-animations-moves.js,
 *      battle-tooltips.js, and the dex data the renderer needs.
 *    Source: https://github.com/smogon/pokemon-showdown-client
 * 2. Load them (script tags or a dynamic import) so `window.Battle` exists.
 * 3. Point the scene's sprite/audio resource prefix at the PS CDN
 *    (https://play.pokemonshowdown.com/) — those assets are NOT in the client
 *    repo and should not be redistributed (see research §5).
 * 4. Replace the placeholder below with a real `new Battle({...})` instance and
 *    feed it lines (see `feedLine` / `BATTLE_API` notes inline).
 */

import { useEffect, useRef, useState } from 'react'

/**
 * The proxy forwards frames verbatim, including the leading `>ROOMID` line.
 * Showdown's `Battle` class wants the bare `|...` protocol lines, so strip the
 * room marker and split multi-line frames. `|ping` is our proxy keepalive and
 * must be ignored.
 */
function protocolLinesFromFrame(frame) {
  return frame
    .split('\n')
    .filter(line => line && !line.startsWith('>') && line !== '|ping')
}

export default function ShowdownBattleScene({ room }) {
  const frameRef = useRef(null)     // scene container (passed as $frame)
  const logRef   = useRef(null)     // text-log container (passed as $logFrame)
  const battleRef = useRef(null)    // the live `Battle` instance (Stage 3)
  const wsRef    = useRef(null)
  // Defaults to 'connecting' because the effect below only runs once `room` is
  // set; status is then advanced by the socket event handlers (not the effect
  // body, which keeps react-hooks/set-state-in-effect happy).
  const [status, setStatus] = useState('connecting')   // connecting|live|ended|error
  const [lineCount, setLineCount] = useState(0)  // PoC: prove the stream flows

  useEffect(() => {
    if (!room) return undefined

    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/showdown/${room}`)
    wsRef.current = ws

    ws.onopen = () => setStatus('live')

    ws.onmessage = (e) => {
      const lines = protocolLinesFromFrame(e.data)
      if (lines.length === 0) return
      setLineCount(n => n + lines.length)

      // --- Stage 3 integration point ---------------------------------------
      // const battle = battleRef.current
      // if (battle) {
      //   for (const line of lines) battle.stepQueue.push(line)
      //   battle.seekTurn(Infinity)   // follow the live tail
      //   battle.play()
      // }
      // ---------------------------------------------------------------------
    }

    ws.onerror = () => setStatus('error')
    ws.onclose = () => setStatus(prev => (prev === 'error' ? 'error' : 'ended'))

    return () => {
      ws.close()
      wsRef.current = null
      // Stage 3: tear down the renderer instance too.
      battleRef.current?.destroy?.()
      battleRef.current = null
    }
  }, [room])

  // Stage 2/3: instantiate the vendored renderer once the bundle is loaded.
  // useEffect(() => {
  //   if (!window.Battle || !frameRef.current) return
  //   battleRef.current = new window.Battle({
  //     $frame: window.jQuery(frameRef.current),
  //     $logFrame: window.jQuery(logRef.current),
  //     id: room,
  //     subscription: (s) => setStatus(s === 'ended' ? 'ended' : 'live'),
  //   })
  //   return () => battleRef.current?.destroy()
  // }, [room])

  if (!room) {
    return (
      <div className="sbs-placeholder">
        Waiting for the Showdown room id…
      </div>
    )
  }

  return (
    <div className="showdown-battle-scene">
      {/* Stage 2: vendored renderer draws into these two containers. */}
      <div ref={frameRef} className="sbs-frame" />
      <div ref={logRef} className="sbs-log" />

      {/* PoC placeholder so the data path is observable before the bundle lands. */}
      <div className="sbs-status">
        Showdown scene ({status}) — room <code>{room}</code> — {lineCount} protocol lines received.
        <br />
        Renderer bundle not yet vendored; see docs/op-02-architecture.md (Stage 2).
      </div>
    </div>
  )
}
