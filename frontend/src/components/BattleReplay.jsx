import { useState, useEffect, useCallback } from 'react'
import PokemonCard from './PokemonCard'

// ---------------------------------------------------------------------------
// HP Timeline SVG — HP lines + win probability overlay + analysis markers
// ---------------------------------------------------------------------------

function HPTimeline({ turns, currentIdx, p1Label, p2Label, analysis }) {
  if (turns.length < 2) return null

  const W = 1000
  const H = 64

  const xOf = (i) => (i / (turns.length - 1)) * W
  const yOf = (hp) => hp == null ? null : H - hp * H

  function buildPath(getter) {
    const pts = []
    turns.forEach((t, i) => {
      const y = yOf(getter(t))
      if (y != null) pts.push(`${xOf(i).toFixed(1)},${y.toFixed(1)}`)
    })
    return pts.length > 1 ? `M ${pts.join(' L ')}` : ''
  }

  const p1Path = buildPath(t => t.p1?.state?.my_active?.hp_fraction ?? null)
  const p2Path = buildPath(t => t.p2?.state?.my_active?.hp_fraction ?? null)
  const markerX = xOf(currentIdx)

  // Win probability overlay from analysis data
  const wpTimeline = analysis?.win_probability_timeline ?? []
  const wpByTurn = {}
  wpTimeline.forEach(t => { wpByTurn[t.turn_number] = t.p1_win_prob })

  // Map wp to turns array indices (turns are sorted by .turn field)
  const wpPts = turns
    .map((t, i) => {
      const prob = wpByTurn[t.turn]
      return prob != null ? `${xOf(i).toFixed(1)},${(H - prob * H).toFixed(1)}` : null
    })
    .filter(Boolean)
  const wpPath = wpPts.length > 1 ? `M ${wpPts.join(' L ')}` : ''

  // Turning point
  const tp = analysis?.turning_point
  const tpTurnIdx = tp != null ? turns.findIndex(t => t.turn === tp) : -1

  // Blunder markers: which turn indices have blunders?
  const blunderTurnNums = new Set((analysis?.blunders ?? []).map(b => b.turn_number))
  const blunderIdxs = turns
    .map((t, i) => (blunderTurnNums.has(t.turn) ? i : null))
    .filter(i => i != null)

  return (
    <div className="hp-timeline">
      <div className="hp-timeline-labels">
        <span className="htl-p1">■ {p1Label} HP</span>
        <span className="htl-p2">■ {p2Label} HP</span>
        {wpPath && <span className="htl-wp">◇ Win prob</span>}
        <span className="htl-axis-note">Active HP / win probability over battle</span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="none"
        className="hp-timeline-svg"
        style={{ height: '64px' }}
      >
        {/* 50 % grid line */}
        <line x1="0" y1={H / 2} x2={W} y2={H / 2}
          stroke="rgba(255,255,255,0.07)" strokeDasharray="6 4" />
        {/* danger zone at 25 % */}
        <line x1="0" y1={H * 0.75} x2={W} y2={H * 0.75}
          stroke="rgba(255,68,85,0.12)" strokeDasharray="4 6" />

        {/* Turning point band */}
        {tpTurnIdx >= 0 && (
          <rect x={xOf(tpTurnIdx) - 2} y="0" width="4" height={H}
            fill="var(--accent-amber)" opacity="0.18" rx="1" />
        )}

        {/* Blunder markers (small orange triangles on top axis) */}
        {blunderIdxs.map(i => (
          <polygon
            key={i}
            points={`${xOf(i)},0 ${xOf(i) - 4},8 ${xOf(i) + 4},8`}
            fill="var(--accent-amber)" opacity="0.7"
          />
        ))}

        {/* Win probability overlay (dashed white line) */}
        {wpPath && (
          <path d={wpPath} fill="none"
            stroke="rgba(255,255,255,0.35)" strokeWidth="1"
            strokeDasharray="4 3"
            strokeLinecap="round" strokeLinejoin="round" />
        )}

        {/* P1 HP */}
        {p1Path && (
          <path d={p1Path} fill="none"
            stroke="var(--accent-cyan)" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
        )}
        {/* P2 HP */}
        {p2Path && (
          <path d={p2Path} fill="none"
            stroke="var(--accent-amber)" strokeWidth="2"
            strokeLinecap="round" strokeLinejoin="round" opacity="0.85" />
        )}

        {/* Current-turn marker */}
        <line x1={markerX} y1="0" x2={markerX} y2={H}
          stroke="rgba(255,255,255,0.55)" strokeWidth="1.5" />
        <circle cx={markerX} cy={yOf(turns[currentIdx]?.p1?.state?.my_active?.hp_fraction) ?? H / 2}
          r="4" fill="var(--accent-cyan)" />
        <circle cx={markerX} cy={yOf(turns[currentIdx]?.p2?.state?.my_active?.hp_fraction) ?? H / 2}
          r="4" fill="var(--accent-amber)" />
      </svg>

      {/* Turning point callout */}
      {tpTurnIdx >= 0 && (
        <div className="htl-turning-point">
          ⚡ Turning point — largest swing at turn {tp}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Turn action display — what each model chose this turn
// ---------------------------------------------------------------------------

const RNG_META = {
  possible_crit: { icon: '⚡', label: 'POSSIBLE CRIT', cls: 'rng-crit' },
  possible_miss: { icon: '✕',  label: 'POSSIBLE MISS', cls: 'rng-miss' },
}

// Declared outside TurnActions so it's not recreated on every render.
function ActionRow({ role, label, data, ann }) {
  if (!data) return null
  const action = data.action?.replace(/^\/choose\s+/, '') ?? '—'
  const rng = ann?.rng_flag ? RNG_META[ann.rng_flag] : null

  return (
    <div className="tap-row">
      <span className={`tap-player ${role}`}>{label}</span>
      <span className="tap-action">
        {action}
        {!data.parse_success && (
          <span className="tap-fallback"> · random fallback</span>
        )}
      </span>
      {ann && ann.decision_quality !== 'no_data' && (
        <span className={`tap-quality tap-q-${ann.decision_quality}`}>
          {ann.decision_quality.toUpperCase()}
          {ann.is_blunder && ' ⚠'}
        </span>
      )}
      {rng && (
        <span className={`tap-rng ${rng.cls}`} title={rng.label}>
          {rng.icon} {rng.label}
        </span>
      )}
    </div>
  )
}

function TurnActions({ turn, p1Label, p2Label, analysisAnns }) {
  if (!turn) return null

  // Find analysis annotations for this turn
  const annsByRole = {}
  if (analysisAnns) {
    for (const a of analysisAnns) {
      if (a.turn_number === turn.turn) annsByRole[a.player_role] = a
    }
  }

  return (
    <div className="turn-actions-panel">
      <div className="tap-title">TURN {turn.turn} — DECISIONS</div>
      <ActionRow role="p1" label={p1Label} data={turn.p1} ann={annsByRole.p1} />
      <ActionRow role="p2" label={p2Label} data={turn.p2} ann={annsByRole.p2} />
    </div>
  )
}

// ---------------------------------------------------------------------------
// Heuristic drawer (reused in replay for the current turn)
// ---------------------------------------------------------------------------

function HeuristicDrawer({ heuristics }) {
  const [open, setOpen] = useState(false)
  if (!heuristics?.move_scores?.length) return null
  return (
    <div className="heuristic-drawer">
      <button className="heuristic-toggle" onClick={() => setOpen(o => !o)}>
        <span>⚙ HEURISTIC ADVISORY</span>
        <span className={`drawer-chevron ${open ? 'open' : ''}`}>▼</span>
      </button>
      {open && (
        <div className="heuristic-content">
          {heuristics.move_scores.map((ms, i) => {
            const isSuper  = ms.effectiveness_label?.includes('super')
            const isImmune = ms.effectiveness_label?.includes('immune')
            return (
              <div key={i} className="heuristic-move">
                <span className="hmove-name">
                  {`move ${i + 1}`} — {ms.move_id.replace(/_/g, ' ')}
                </span>
                <span className={`hmove-effectiveness ${isSuper ? 'super' : isImmune ? 'immune' : ''}`}>
                  {ms.effectiveness_label}
                  {ms.estimated_damage_pct && ` · ${ms.estimated_damage_pct}`}
                </span>
                <span className="hmove-notes">{(ms.notes || []).join(' · ')}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main BattleReplay
// ---------------------------------------------------------------------------

const PLAY_SPEED_MS = 1800

export default function BattleReplay({ battleId, onClose }) {
  const [data,     setData]     = useState(null)
  const [analysis, setAnalysis] = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [error,    setError]    = useState(null)
  const [idx,      setIdx]      = useState(0)
  const [playing,  setPlaying]  = useState(false)

  // Keyboard navigation
  const handleKey = useCallback((e) => {
    if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
      setPlaying(false)
      setIdx(i => Math.min((data?.turns.length ?? 1) - 1, i + 1))
    } else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
      setPlaying(false)
      setIdx(i => Math.max(0, i - 1))
    } else if (e.key === ' ') {
      e.preventDefault()
      setPlaying(p => !p)
    } else if (e.key === 'Escape') {
      onClose()
    }
  }, [data, onClose])

  useEffect(() => {
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [handleKey])

  // Fetch replay data + analysis in parallel
  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const [replayData, analysisData] = await Promise.all([
          fetch(`/api/battles/${battleId}/replay`).then(r => { if (!r.ok) throw new Error(r.status); return r.json() }),
          fetch(`/api/battles/${battleId}/analysis`).then(r => r.ok ? r.json() : null).catch(() => null),
        ])
        if (cancelled) return
        setData(replayData)
        setAnalysis(analysisData)
        setIdx(0)
      } catch(e) {
        if (!cancelled) setError(e.message)
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [battleId])

  // Auto-play
  useEffect(() => {
    if (!playing || !data) return
    // Defer setPlaying so it isn't synchronous within the effect body.
    if (idx >= data.turns.length - 1) {
      const t = setTimeout(() => setPlaying(false), 0)
      return () => clearTimeout(t)
    }
    const t = setTimeout(() => setIdx(i => i + 1), PLAY_SPEED_MS)
    return () => clearTimeout(t)
  }, [playing, idx, data])

  // ---- Loading / error states ----
  if (loading) {
    return (
      <div className="replay-loading">
        <div className="replay-loading-inner">
          <div className="replay-loading-dot" /><div className="replay-loading-dot" /><div className="replay-loading-dot" />
          <div style={{ marginTop: '0.75rem', fontSize: '0.65rem' }}>Loading replay…</div>
        </div>
      </div>
    )
  }
  if (error || !data) {
    return (
      <div className="replay-loading">
        <div className="replay-loading-inner">
          <div style={{ color: 'var(--accent-red)', marginBottom: '0.75rem' }}>Failed to load replay</div>
          <button className="btn-dismiss" onClick={onClose}>CLOSE</button>
        </div>
      </div>
    )
  }

  // ---- Main render ----
  const turns   = data.turns
  const turn    = turns[idx]
  const battle  = data.battle

  // Short names for labels
  const p1Label = battle.p1?.split('/').pop() ?? 'P1'
  const p2Label = battle.p2?.split('/').pop() ?? 'P2'

  // Construct state objects in the shape BattleField/PokemonCard expect
  const p1State = turn?.p1?.state ? { player_role: 'p1', turn: turn.turn, state: turn.p1.state } : null
  const p2State = turn?.p2?.state ? { player_role: 'p2', turn: turn.turn, state: turn.p2.state } : null

  const p1Mon   = p1State?.state?.my_active ?? null
  const p2Mon   = p2State?.state?.my_active ?? null
  const oppOfP1 = p1State?.state?.opponent_active ?? null
  const weather = p1State?.state?.weather ?? p2State?.state?.weather ?? null
  const p1Bench = (p1State?.state?.my_team ?? []).filter(m => m.species !== p1Mon?.species)
  const p2Bench = (p2State?.state?.my_team ?? []).filter(m => m.species !== p2Mon?.species)

  // Heuristic from p1's perspective (their own decision context)
  const heuristics = p1State?.state?.heuristics

  const isFirst = idx === 0
  const isLast  = idx === turns.length - 1

  function seek(newIdx) { setPlaying(false); setIdx(newIdx) }

  return (
    <div className="replay-wrapper">
      {/* ---- Header ---- */}
      <div className="replay-header">
        <div className="replay-title-group">
          <span className="replay-title">▶ REPLAY</span>
          <span className="replay-battle-id">Battle #{battle.id}</span>
          <span className="replay-matchup">
            <span className="replay-p1">{p1Label}</span>
            <span className="replay-vs">vs</span>
            <span className="replay-p2">{p2Label}</span>
          </span>
          {battle.winner != null && (
            <span className="replay-winner-badge">
              {battle.winner === 1 ? p1Label : p2Label} won · {battle.total_turns} turns
            </span>
          )}
        </div>
        <button className="btn-close-replay" onClick={onClose} title="Close (Esc)">✕ CLOSE</button>
      </div>

      {/* ---- Arena ---- */}
      <div className="replay-arena-wrap">
        {/* Weather */}
        {weather && (
          <div className="replay-weather">🌤 {weather}</div>
        )}

        <div className="arena">
          <PokemonCard mon={p1Mon} side="p1" isOpponent={false} bench={p1Bench} />
          <div className="vs-divider">VS</div>
          <PokemonCard
            mon={p2Mon ?? oppOfP1}
            side="p2"
            isOpponent={!p2Mon}
            bench={p2Bench}
          />
        </div>

        {/* Bottom: heuristic drawer */}
        {heuristics?.move_scores?.length > 0 && (
          <div className="bottom-panels" style={{ gridTemplateColumns: '1fr' }}>
            <HeuristicDrawer heuristics={heuristics} />
          </div>
        )}
      </div>

      {/* ---- HP Timeline ---- */}
      <HPTimeline
        turns={turns}
        currentIdx={idx}
        p1Label={p1Label}
        p2Label={p2Label}
        analysis={analysis}
      />

      {/* ---- Controls ---- */}
      <div className="replay-controls">
        <div className="replay-buttons">
          <button className="replay-btn" onClick={() => seek(0)} disabled={isFirst} title="First turn">⏮</button>
          <button className="replay-btn" onClick={() => seek(idx - 1)} disabled={isFirst} title="Previous turn (←)">◀</button>
          <button
            className={`replay-btn replay-play-btn ${playing ? 'playing' : ''}`}
            onClick={() => setPlaying(p => !p)}
            title={playing ? 'Pause (Space)' : 'Play (Space)'}
          >
            {playing ? '⏸' : '▶'}
          </button>
          <button className="replay-btn" onClick={() => seek(idx + 1)} disabled={isLast} title="Next turn (→)">▶</button>
          <button className="replay-btn" onClick={() => seek(turns.length - 1)} disabled={isLast} title="Last turn">⏭</button>
        </div>

        <div className="replay-scrub-row">
          <span className="replay-turn-label">TURN</span>
          <input
            type="range"
            min={0}
            max={turns.length - 1}
            value={idx}
            onChange={e => seek(Number(e.target.value))}
            className="replay-slider"
          />
          <span className="replay-turn-counter">
            {turn?.turn ?? '?'} / {turns[turns.length - 1]?.turn ?? '?'}
          </span>
        </div>

        <div className="replay-kbd-hint">← → to step · Space to play/pause · Esc to close</div>
      </div>

      {/* ---- Turn actions ---- */}
      <TurnActions
        turn={turn}
        p1Label={p1Label}
        p2Label={p2Label}
        analysisAnns={analysis?.turns}
      />
    </div>
  )
}
