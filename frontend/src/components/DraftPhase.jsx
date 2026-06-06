/**
 * DraftPhase — overlay shown while both players are drafting their teams.
 *
 * Receives `draft` from useBattleStream:
 *   {
 *     tier: 'ou',
 *     battleId: 42,
 *     p1: { picks: [{species, types}], done: false },
 *     p2: { picks: [{species, types}], done: false },
 *   }
 *
 * When both sides are done, the battle_start event will fire and the parent
 * clears `draft` — this overlay disappears automatically.
 */

import { useEffect, useRef } from 'react'

// Pokémon type → color mapping (same palette as PokemonCard)
const TYPE_COLORS = {
  Normal: '#A8A878', Fire: '#F08030', Water: '#6890F0', Electric: '#F8D030',
  Grass: '#78C850', Ice: '#98D8D8', Fighting: '#C03028', Poison: '#A040A0',
  Ground: '#E0C068', Flying: '#A890F0', Psychic: '#F85888', Bug: '#A8B820',
  Rock: '#B8A038', Ghost: '#705898', Dragon: '#7038F8', Dark: '#705848',
  Steel: '#B8B8D0', Fairy: '#EE99AC',
}

function TypeBadge({ type }) {
  const bg = TYPE_COLORS[type] || '#888'
  return (
    <span className="dp-type-badge" style={{ background: bg }}>
      {type.toUpperCase()}
    </span>
  )
}

function PickCard({ pick, index, animate }) {
  return (
    <div className={`dp-pick-card ${animate ? 'dp-pick-card--in' : ''}`}
         style={{ animationDelay: `${index * 60}ms` }}>
      <span className="dp-pick-num">{index + 1}</span>
      <span className="dp-pick-species">{pick.species}</span>
      <span className="dp-pick-types">
        {pick.types.map(t => <TypeBadge key={t} type={t} />)}
      </span>
    </div>
  )
}

function PlayerColumn({ role, side, label }) {
  const picks = side?.picks ?? []
  const done = side?.done ?? false
  const prevLen = useRef(0)

  useEffect(() => {
    prevLen.current = picks.length
  })

  const emptySlots = 6 - picks.length

  return (
    <div className={`dp-column dp-column--${role}`}>
      <div className="dp-column-header">
        <span className="dp-column-role">{label}</span>
        {done
          ? <span className="dp-done-badge">✓ READY</span>
          : <span className="dp-picking-badge">
              <span className="dp-dot" />PICKING…
            </span>
        }
      </div>

      <div className="dp-picks-list">
        {picks.map((pick, i) => (
          <PickCard
            key={pick.species + i}
            pick={pick}
            index={i}
            animate={i >= prevLen.current - 1}
          />
        ))}
        {Array.from({ length: emptySlots }).map((_, i) => (
          <div key={`empty-${i}`} className="dp-pick-empty">
            <span className="dp-pick-num">{picks.length + i + 1}</span>
            <span className="dp-empty-label">—</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function DraftPhase({ draft, p1Label, p2Label }) {
  if (!draft) return null

  const { tier, p1, p2 } = draft
  const tierLabel = tier ? tier.toUpperCase() : 'DRAFTED'
  const bothDone = p1?.done && p2?.done

  return (
    <div className="dp-overlay">
      <div className="dp-header">
        <div className="dp-title">
          <span className="dp-tier-badge">{tierLabel}</span>
          TEAM DRAFT
        </div>
        {bothDone && (
          <div className="dp-both-ready">Both teams ready — battle starting…</div>
        )}
      </div>

      <div className="dp-columns">
        <PlayerColumn
          role="p1"
          side={p1}
          label={p1Label || 'PLAYER 1'}
        />
        <div className="dp-vs-divider">VS</div>
        <PlayerColumn
          role="p2"
          side={p2}
          label={p2Label || 'PLAYER 2'}
        />
      </div>

      <div className="dp-footer">
        Pick 6 Pokémon from the {tierLabel} tier pool — team composition sets the strategy.
      </div>
    </div>
  )
}
