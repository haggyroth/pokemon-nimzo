/**
 * Shared battle *lifecycle chrome* — the controls and overlays that wrap a
 * battle regardless of which stage renders it (Classic BattleField or the
 * Showdown cockpit). Lives here so the two views can't drift: cancel, winner
 * banner, tournament progress, and the tier/draft badges all have one home.
 *
 * App.jsx owns the cross-cutting overlays (TournamentBar, WinnerBanner,
 * TournamentEndOverlay) by wrapping both stages. Each stage's own header
 * renders the inline controls (CancelBattleButton, BattleBadges).
 */

import { useState, useEffect } from 'react'

// Module-local (not exported): a non-component export would break the
// react-refresh/only-export-components rule. Each view that needs tier
// labels elsewhere keeps its own copy.
const TIER_LABELS = {
  random:     'RANDOM',
  ou:         'OU',
  ubers:      'UBERS',
  uu:         'UU',
  nu:         'NU',
  lc:         'LC',
  freeforall: 'FREE-FOR-ALL',
}

export function TierBadge({ tier, className = '' }) {
  if (!tier || tier === 'random') return null
  return (
    <span className={`tier-badge tier-badge--${tier} ${className}`}>
      {TIER_LABELS[tier] ?? tier.toUpperCase()}
    </span>
  )
}

/** Tier + draft badges for a battle header (shared by both stages). */
export function BattleBadges({ tier, drafted }) {
  if ((!tier || tier === 'random') && !drafted) return null
  return (
    <div className="battle-header-badges">
      <TierBadge tier={tier} />
      {drafted && <span className="draft-badge">DRAFT</span>}
    </div>
  )
}

async function cancelBattle(battleId) {
  if (!battleId) return
  await fetch(`/api/battles/${battleId}/cancel`, { method: 'POST' })
}

/** Stop-the-battle control — rendered in each stage's header when live. */
export function CancelBattleButton({ battleId }) {
  if (!battleId) return null
  return (
    <button
      className="btn-cancel-battle"
      title="Cancel this battle"
      onClick={() => cancelBattle(battleId)}
    >
      ■ CANCEL
    </button>
  )
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

/** Tournament progress bar — shown above the stage while a tournament runs. */
export function TournamentBar({ tournament, onScoreboard }) {
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

/** End-of-battle result modal — winner/cancelled, turn count, replay, rosters. */
export function WinnerBanner({
  battleResult, battleInfo, battleTier, battleDrafted,
  onDismiss, onReplaySelected, currentBattleId,
}) {
  // Fetch drafted teams when a result arrives (only for drafted battles)
  const teams = useTeams(currentBattleId, !!battleResult && !!battleDrafted)
  if (!battleResult) return null

  return (
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
        <div className="winner-actions">
          {onReplaySelected && currentBattleId && (
            <button
              className="btn-replay"
              onClick={() => onReplaySelected(currentBattleId)}
              title="Watch replay (R)"
            >▶ REPLAY</button>
          )}
          <button className="btn-dismiss" onClick={onDismiss}>CLOSE</button>
        </div>
      </div>
    </div>
  )
}

/** Tournament completion modal — final top-5 leaderboard. */
export function TournamentEndOverlay({ tournament }) {
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
