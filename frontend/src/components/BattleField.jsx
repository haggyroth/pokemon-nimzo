import { useState, useEffect } from 'react'
import PokemonCard from './PokemonCard'
import BattleLog from './BattleLog'

const TIER_LABELS = {
  random:     'RANDOM',
  ou:         'OU',
  ubers:      'UBERS',
  uu:         'UU',
  nu:         'NU',
  lc:         'LC',
  freeforall: 'FREE-FOR-ALL',
}

function TierBadge({ tier, className = '' }) {
  if (!tier || tier === 'random') return null
  return (
    <span className={`tier-badge tier-badge--${tier} ${className}`}>
      {TIER_LABELS[tier] ?? tier.toUpperCase()}
    </span>
  )
}

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

// ---------------------------------------------------------------------------
// Win-probability bar
// ---------------------------------------------------------------------------

function teamHpScore(state) {
  if (!state) return null
  const team = state.my_team ?? []
  if (team.length > 0) {
    return team.reduce((acc, m) => acc + Math.max(0, m.hp_fraction ?? 0), 0)
  }
  const active = state.my_active
  return active ? Math.max(0, active.hp_fraction ?? 0.5) : null
}

function WinProbBar({ p1State, p2State, p1Label, p2Label }) {
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

function ThinkingBadge({ role, isCoach }) {
  if (!role) return null
  if (isCoach) {
    return (
      <div className="thinking-badge thinking-badge--coach">
        <span className="thinking-badge-icon">🎓</span>
        <span style={{ marginLeft: '0.35rem', fontSize: '0.65rem', opacity: 0.85, letterSpacing: '0.04em' }}>
          {role.toUpperCase()} COACH ANALYZING
        </span>
      </div>
    )
  }
  return (
    <div className="thinking-badge">
      <span className="thinking-badge-dot" />
      <span className="thinking-badge-dot" />
      <span className="thinking-badge-dot" />
      <span style={{ marginLeft: '0.4rem', fontSize: '0.65rem', opacity: 0.7 }}>
        {role.toUpperCase()} THINKING
      </span>
    </div>
  )
}

async function cancelBattle(battleId) {
  if (!battleId) return
  await fetch(`/api/battles/${battleId}/cancel`, { method: 'POST' })
}

function useTeams(battleId, enabled) {
  const [teams, setTeams] = useState(null)
  useEffect(() => {
    if (!battleId || !enabled) return
    fetch(`/api/battles/${battleId}/teams`)
      .then(r => r.ok ? r.json() : null)
      .then(d => { if (d) setTeams(d) })
      .catch(() => {})
  }, [battleId, enabled])
  return teams
}

export default function BattleField({
  p1State, p2State, battleInfo, battleResult, events, thinking, coachThinking,
  onDismiss, tournament, onTournamentScoreboard,
}) {
  const p1Mon   = p1State?.state?.my_active ?? null
  const p2Mon   = p2State?.state?.my_active ?? null
  const oppOfP1 = p1State?.state?.opponent_active ?? null
  const weather = p1State?.state?.weather ?? p2State?.state?.weather ?? null
  const turn    = Math.max(p1State?.turn ?? 0, p2State?.turn ?? 0)

  const p1Bench = (p1State?.state?.my_team ?? []).filter(m => m.species !== p1Mon?.species)
  const p2Bench = (p2State?.state?.my_team ?? []).filter(m => m.species !== p2Mon?.species)

  const lastState = (p1State?.turn ?? 0) >= (p2State?.turn ?? 0)
    ? p1State?.state
    : p2State?.state

  const isLive = battleInfo && !battleResult
  const currentBattleId = battleInfo?.battle_id
  const battleTier = battleInfo?.tier
  const battleDrafted = battleInfo?.drafted

  // Fetch drafted teams when a result arrives (only for drafted battles)
  const teams = useTeams(currentBattleId, !!battleResult && !!battleDrafted)

  return (
    <div className="battlefield-wrapper">
      {/* Tournament progress bar — shows when a tournament is running */}
      {tournament && tournament.status !== 'completed' && (
        <TournamentBar tournament={tournament} onScoreboard={onTournamentScoreboard} />
      )}

      {/* Header row */}
      <div className="battle-header">
        <div className="turn-counter">
          {turn > 0 ? `TURN ${turn}` : 'READY'}
        </div>
        <div className="battle-header-center">
          <div className="battle-header-badges">
            <TierBadge tier={battleTier} />
            {battleDrafted && <span className="draft-badge">DRAFT</span>}
          </div>
          {weather && <div className="weather-badge">🌤 {weather}</div>}
          <ThinkingBadge role={coachThinking || thinking} isCoach={!!coachThinking} />
        </div>
        <div className="battle-header-right">
          <div className="battle-status-text">
            {battleInfo
              ? `${battleInfo.p1} vs ${battleInfo.p2}`
              : 'Waiting for battle…'}
          </div>
          {isLive && (
            <button
              className="btn-cancel-battle"
              title="Cancel this battle"
              onClick={() => cancelBattle(currentBattleId)}
            >
              ■ CANCEL
            </button>
          )}
        </div>
      </div>

      {/* Win-probability bar — shown once both players have emitted at least one turn */}
      <WinProbBar
        p1State={p1State}
        p2State={p2State}
        p1Label={battleInfo?.p1}
        p2Label={battleInfo?.p2}
      />

      {/* Arena */}
      <div className="arena">
        <PokemonCard
          mon={p1Mon}
          side="p1"
          isOpponent={false}
          isThinking={thinking === 'p1' || coachThinking === 'p1'}
          bench={p1Bench}
        />
        <div className="vs-divider">VS</div>
        <PokemonCard
          mon={p2Mon ?? oppOfP1}
          side="p2"
          isOpponent={!p2Mon}
          isThinking={thinking === 'p2' || coachThinking === 'p2'}
          bench={p2Bench}
        />
      </div>

      {/* Bottom panels */}
      <div
        className="bottom-panels"
        style={!lastState?.heuristics?.move_scores?.length ? { gridTemplateColumns: '1fr' } : {}}
      >
        <BattleLog events={events} />
        <HeuristicDrawer heuristics={lastState?.heuristics} />
      </div>

      {/* Winner / cancelled banner */}
      {battleResult && (
        <div className="winner-banner" onClick={onDismiss}>
          <div className="winner-card" onClick={e => e.stopPropagation()}>
            {battleResult.cancelled ? (
              <>
                <div className="winner-label">BATTLE CANCELLED</div>
                <div className="winner-name" style={{ color: 'var(--text-dim)' }}>Stopped by user</div>
              </>
            ) : (
              <>
                <div className="winner-label">BATTLE COMPLETE</div>
                {battleTier && battleTier !== 'random' && (
                  <TierBadge tier={battleTier} className="winner-tier-badge" />
                )}
                <div className="winner-name">
                  {battleResult.winner === 1
                    ? (battleInfo?.p1 ?? 'P1') + ' WINS'
                    : battleResult.winner === 2
                      ? (battleInfo?.p2 ?? 'P2') + ' WINS'
                      : 'DRAW'}
                </div>
                <div className="winner-turns">{battleResult.total_turns} turns</div>

                {/* Drafted team rosters */}
                {teams && (teams.p1 || teams.p2) && (
                  <div className="winner-teams">
                    {[['p1', battleInfo?.p1], ['p2', battleInfo?.p2]].map(([role, label]) => {
                      const team = teams[role]
                      if (!team) return null
                      const pokemon = Array.isArray(team.pokemon) ? team.pokemon : []
                      return (
                        <div key={role} className={`winner-team winner-team--${role}`}>
                          <div className="winner-team-label">{label?.split('/').pop() ?? role.toUpperCase()}</div>
                          <div className="winner-team-mons">
                            {pokemon.map(sid => (
                              <span key={sid} className="winner-team-mon">{sid}</span>
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                )}
              </>
            )}
            <button className="btn-dismiss" onClick={onDismiss}>CLOSE</button>
          </div>
        </div>
      )}

      {/* Tournament completion overlay */}
      {tournament?.status === 'completed' && (
        <TournamentEndOverlay tournament={tournament} />
      )}
    </div>
  )
}

function TournamentBar({ tournament, onScoreboard }) {
  const pct = tournament.total > 0
    ? Math.round((tournament.done / tournament.total) * 100)
    : 0
  const tier = tournament.tier
  const tierLabel = TIER_LABELS[tier] ?? tier?.toUpperCase()

  return (
    <div className="tournament-bar" onClick={onScoreboard} style={{ cursor: onScoreboard ? 'pointer' : 'default' }} title={onScoreboard ? 'View scoreboard' : undefined}>
      <div className="tournament-bar-info">
        <span className="tournament-bar-label">TOURNAMENT</span>
        {tier && tier !== 'random' && (
          <span className={`tournament-bar-tier tier-badge tier-badge--${tier}`}>{tierLabel}</span>
        )}
        <span className="tournament-bar-progress">
          {tournament.done} / {tournament.total} battles
          {tournament.p1 && (
            <span className="tournament-bar-matchup"> · {tournament.p1.split('/').pop()} vs {tournament.p2?.split('/').pop()}</span>
          )}
        </span>
        {tournament.status === 'cancelled' && (
          <span className="tournament-bar-cancelled">CANCELLED</span>
        )}
        {onScoreboard && (
          <span className="tournament-bar-scores-hint">SCORES →</span>
        )}
      </div>
      <div className="tournament-progress-track">
        <div
          className="tournament-progress-fill"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

function TournamentEndOverlay({ tournament }) {
  const [dismissed, setDismissed] = useState(false)
  if (dismissed) return null

  const lb = tournament.leaderboard ?? []
  const medals = ['🥇', '🥈', '🥉']

  return (
    <div className="winner-banner" onClick={() => setDismissed(true)}>
      <div className="winner-card tournament-end-card" onClick={e => e.stopPropagation()}>
        <div className="winner-label">TOURNAMENT COMPLETE</div>
        <div className="tournament-final-lb">
          {lb.slice(0, 5).map((r, i) => (
            <div key={i} className="tournament-lb-row">
              <span className="tlb-medal">{medals[i] ?? `${i + 1}`}</span>
              <span className="tlb-name">{r.model_name}</span>
              <span className="tlb-elo">{r.rating.toFixed(0)}</span>
              <span className="tlb-wlt">
                <span className="w">{r.wins}W</span>
                {' '}<span className="l">{r.losses}L</span>
              </span>
            </div>
          ))}
        </div>
        <button className="btn-dismiss" onClick={() => setDismissed(true)}>CLOSE</button>
      </div>
    </div>
  )
}
