import { useState } from 'react'
import PokemonCard from './PokemonCard'
import BattleLog from './BattleLog'

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
            const isSuper = ms.effectiveness_label?.includes('super')
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
                <span className="hmove-notes">
                  {(ms.notes || []).join(' · ')}
                </span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

export default function BattleField({ p1State, p2State, battleInfo, battleResult, events, onDismiss }) {
  // p1State.state.my_active = p1's own active mon
  // p2State.state.my_active = p2's own active mon (shown on right)
  const p1Mon   = p1State?.state?.my_active ?? null
  const p2Mon   = p2State?.state?.my_active ?? null
  const oppOfP1 = p1State?.state?.opponent_active ?? null  // p2 from p1's view
  const weather = p1State?.state?.weather ?? p2State?.state?.weather ?? null
  const turn    = Math.max(p1State?.turn ?? 0, p2State?.turn ?? 0)

  // Last heuristics come from the most recent turn event (whichever arrived last)
  const lastState = (p1State?.turn ?? 0) >= (p2State?.turn ?? 0)
    ? p1State?.state
    : p2State?.state

  return (
    <div className="battlefield-wrapper">
      {/* Header row */}
      <div className="battle-header">
        <div className="turn-counter">
          {turn > 0 ? `TURN ${turn}` : 'READY'}
        </div>
        {weather && <div className="weather-badge">🌤 {weather}</div>}
        <div className="battle-status-text">
          {battleInfo
            ? `${battleInfo.p1} vs ${battleInfo.p2}`
            : 'Waiting for battle…'}
        </div>
      </div>

      {/* Arena */}
      <div className="arena">
        <PokemonCard mon={p1Mon} side="p1" isOpponent={false} />
        <div className="vs-divider">VS</div>
        {/* Right side: use p2's own state if available, else p1's opponent view */}
        <PokemonCard mon={p2Mon ?? oppOfP1} side="p2" isOpponent={!p2Mon} />
      </div>

      {/* Bottom panels */}
      <div className="bottom-panels" style={!lastState?.heuristics?.move_scores?.length ? { gridTemplateColumns: '1fr' } : {}}>
        <BattleLog events={events} />
        <HeuristicDrawer heuristics={lastState?.heuristics} />
      </div>

      {/* Winner banner */}
      {battleResult && (
        <div className="winner-banner" onClick={onDismiss}>
          <div className="winner-card" onClick={e => e.stopPropagation()}>
            <div className="winner-label">BATTLE COMPLETE</div>
            <div className="winner-name">
              {battleResult.winner === 1
                ? (battleInfo?.p1 ?? 'P1') + ' WINS'
                : battleResult.winner === 2
                  ? (battleInfo?.p2 ?? 'P2') + ' WINS'
                  : 'DRAW'}
            </div>
            <div className="winner-turns">{battleResult.total_turns} turns</div>
            <button className="btn-dismiss" onClick={onDismiss}>
              CLOSE
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
