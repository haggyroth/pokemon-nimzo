/**
 * ShowdownRenderSpike — OP-02 (#84) Stage 2 render spike.
 *
 * Proves that the vendored (CDN) PS battle renderer can be instantiated from
 * React and will display a known static replay.  This component is the
 * acceptance criterion for Stage 2 before wiring to the live proxy in Stage 3.
 *
 * To view: click "Showdown" in the nav bar during any battle (or navigate
 * directly to view='showdown-spike' in App.jsx).
 */

import { useEffect, useRef, useState } from 'react'
import { useShowdownBundle } from '../hooks/useShowdownBundle'

// A minimal but complete Gen 3 random-battle replay that exercises:
// - player headers, teamsize, gametype, gen, tier
// - initial switches (Blaziken vs Starmie — canonical Gen 3 contenders)
// - one offensive turn to prove move animations fire
// - a win condition so BattleLog shows the full sequence
//
// Using a static log means no Showdown server is needed to verify Stage 2.
const SPIKE_LOG = `|player|p1|NidozoP1||
|player|p2|NidozoP2||
|teamsize|p1|6
|teamsize|p2|6
|gametype|singles
|gen|3
|tier|[Gen 3] Random Battle
|start
|switch|p1a: Blaziken|Blaziken, L50, M|155/155
|switch|p2a: Starmie|Starmie, L50|115/115
|turn|1
|move|p1a: Blaziken|Flamethrower|p2a: Starmie
|-resisted|p2a: Starmie
|-damage|p2a: Starmie|87/115
|move|p2a: Starmie|Surf|p1a: Blaziken
|-supereffective|p1a: Blaziken
|-damage|p1a: Blaziken|42/155
|turn|2
|move|p1a: Blaziken|Sky Uppercut|p2a: Starmie
|-damage|p2a: Starmie|11/115
|move|p2a: Starmie|Recover|p2a: Starmie
|-heal|p2a: Starmie|69/115
|turn|3
|move|p1a: Blaziken|Blaze Kick|p2a: Starmie
|-supereffective|p2a: Starmie
|-damage|p2a: Starmie|0 fnt
|faint|p2a: Starmie
|win|p1`

export default function ShowdownRenderSpike() {
  const { ready, error: bundleError } = useShowdownBundle()
  const frameRef = useRef(null)
  const logRef = useRef(null)
  const battleRef = useRef(null)
  const [status, setStatus] = useState('loading-bundle')
  const [renderError, setRenderError] = useState(null)

  useEffect(() => {
    if (!ready || !frameRef.current || !logRef.current) return
    if (battleRef.current) return   // already mounted

    try {
      const $ = window.jQuery
      if (!$ || !window.Battle) {
        queueMicrotask(() => {
          setRenderError(new Error('window.jQuery or window.Battle missing after bundle load'))
          setStatus('error')
        })
        return
      }

      const battle = new window.Battle({
        $frame: $(frameRef.current),
        $logFrame: $(logRef.current),
        id: 'nidozo-spike',
        paused: true,
      })
      battleRef.current = battle

      // Feed the static replay line by line.
      for (const line of SPIKE_LOG.split('\n')) {
        if (line.trim()) battle.add(line)
      }

      // Seek to the final state instantly (no animation) so we see the
      // end-of-battle snapshot without waiting for the turn timer.
      battle.seekTurn(Infinity, true)
      queueMicrotask(() => setStatus('rendered'))
    } catch (err) {
      queueMicrotask(() => {
        setRenderError(err)
        setStatus('error')
      })
    }

    return () => {
      battleRef.current?.destroy?.()
      battleRef.current = null
    }
  }, [ready])

  if (bundleError) {
    return (
      <div className="srs-wrapper">
        <div className="srs-error">
          <strong>Bundle load failed:</strong> {bundleError.message}
          <br />
          Check that <code>play.pokemonshowdown.com</code> is reachable and the CDN script order in <code>useShowdownBundle.js</code> is correct.
        </div>
      </div>
    )
  }

  return (
    <div className="srs-wrapper">
      <div className="srs-header">
        <h2 className="srs-title">Stage 2 Render Spike</h2>
        <p className="srs-subtitle">
          Static Gen 3 replay — Blaziken vs Starmie.
          {status === 'loading-bundle' && ' Loading PS bundle from CDN…'}
          {status === 'rendered' && ' ✓ Renderer initialised successfully.'}
          {status === 'error' && ` ✗ Render error: ${renderError?.message}`}
        </p>
        <div className={`srs-badge srs-badge--${status}`}>
          {status === 'loading-bundle' ? 'LOADING' : status === 'rendered' ? 'OK' : 'ERROR'}
        </div>
      </div>

      {/* The PS Battle class draws the animated scene into these two divs.
          Dimensions mimic a standard PS replay iframe (640 × 400 + log). */}
      <div className="srs-scene">
        <div ref={frameRef} className="srs-frame" />
        <div ref={logRef} className="srs-log" />
      </div>

      {status === 'loading-bundle' && (
        <div className="srs-loading">
          Loading Pokémon Showdown battle renderer (~4 MB from CDN)…
        </div>
      )}
    </div>
  )
}
