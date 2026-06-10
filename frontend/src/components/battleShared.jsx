/**
 * Shared battle-data presentational components, used by BOTH the Classic
 * BattleField and the Showdown cockpit so the two views stay in parity (same
 * data, same rendering — no drift). All read from the app EventBus state shapes
 * (`p1State`/`p2State` = { turn, state: { my_active, my_team, ... } }).
 */

/** Team-HP score for win-probability: sum of bench hp_fractions, or active HP. */
function teamHpScore(state) {
  if (!state) return null
  const team = state.my_team ?? []
  if (team.length > 0) {
    return team.reduce((acc, m) => acc + Math.max(0, m.hp_fraction ?? 0), 0)
  }
  const active = state.my_active
  return active ? Math.max(0, active.hp_fraction ?? 0.5) : null
}

/** Win-probability bar from the two players' team-HP ratio. */
export function WinProbBar({ p1State, p2State, p1Label, p2Label }) {
  const s1 = teamHpScore(p1State?.state)
  const s2 = teamHpScore(p2State?.state)

  if (s1 === null || s2 === null) return null

  const total = s1 + s2
  const p1Prob = total === 0 ? 0.5 : s1 / total
  const p1Pct  = Math.round(p1Prob * 100)
  const p2Pct  = 100 - p1Pct

  const p1Name = p1Label?.split('/').pop() ?? 'P1'
  const p2Name = p2Label?.split('/').pop() ?? 'P2'

  return (
    <div className="win-prob-bar">
      <div className="win-prob-pcts">
        <span className="win-prob-pct win-prob-pct--p1">
          <span className="win-prob-name">{p1Name}</span>
          <span className="win-prob-num">{p1Pct}%</span>
        </span>
        <span className="win-prob-mid-label">WIN PROB</span>
        <span className="win-prob-pct win-prob-pct--p2">
          <span className="win-prob-num">{p2Pct}%</span>
          <span className="win-prob-name">{p2Name}</span>
        </span>
      </div>
      <div className="win-prob-track">
        <div className="win-prob-fill win-prob-fill--p1" style={{ width: `${p1Pct}%` }} />
        <div className="win-prob-fill win-prob-fill--p2" style={{ width: `${p2Pct}%` }} />
        <div className="win-prob-midline" />
      </div>
    </div>
  )
}

/** Provider + model name label for one side. */
export function PlayerLabel({ label, side }) {
  if (!label) return null
  // "anthropic/claude-sonnet-4-6" → provider="anthropic", name="claude-sonnet-4-6"
  const slash = label.indexOf('/')
  const provider = slash >= 0 ? label.slice(0, slash) : ''
  const name     = slash >= 0 ? label.slice(slash + 1) : label
  return (
    <div className={`player-label player-label--${side}`}>
      {provider && <span className="player-label-provider">{provider}</span>}
      <span className="player-label-name">{name}</span>
    </div>
  )
}
