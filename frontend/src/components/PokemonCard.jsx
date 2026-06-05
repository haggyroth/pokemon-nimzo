import HPBar from './HPBar'

// Official Pokémon type colours
const TYPE_COLORS = {
  NORMAL: '#9a9a7a', FIRE: '#ff6b35', WATER: '#4d9de0', ELECTRIC: '#f7c948',
  GRASS: '#4caf50', ICE: '#80deea', FIGHTING: '#e53935', POISON: '#ab47bc',
  GROUND: '#c6a34a', FLYING: '#9575cd', PSYCHIC: '#e91e8c', BUG: '#8bc34a',
  ROCK: '#a1887f', GHOST: '#5e35b1', DRAGON: '#5c6bc0', DARK: '#6d4c41',
  STEEL: '#90a4ae', FAIRY: '#f48fb1',
}

function TypeBadge({ type }) {
  const color = TYPE_COLORS[type] || '#666'
  return (
    <span
      className="type-badge"
      style={{ background: color }}
    >
      {type}
    </span>
  )
}

function StatusBadge({ status }) {
  if (!status) return null
  const short = { BURNED: 'BRN', PARALYZED: 'PAR', POISONED: 'PSN',
                  TOXIC: 'TOX', ASLEEP: 'SLP', FROZEN: 'FRZ', FAINTED: 'FNT' }
  const label = short[status] || status.slice(0, 3)
  const cls   = short[status] ? status.slice(0, 3) : status.slice(0, 3)
  return <span className={`status-badge status-${label}`}>{label}</span>
}

export default function PokemonCard({ mon, side, isOpponent = false }) {
  if (!mon) {
    return (
      <div className={`pokemon-card ${side} empty`}>
        waiting…
      </div>
    )
  }

  const boostEntries = Object.entries(mon.boosts || {}).filter(([, v]) => v !== 0)
  const revealedMoves = isOpponent
    ? Object.values(mon.revealed_moves || {})
    : null

  return (
    <div className={`pokemon-card ${side}`}>
      <div className="card-header">
        <div>
          <div className="pokemon-name">{mon.species}</div>
          <div className="pokemon-level">Lv.{mon.level ?? 50}</div>
          {mon.status && <StatusBadge status={mon.status} />}
        </div>
        <div className="type-badges">
          {(mon.types || []).map(t => <TypeBadge key={t} type={t} />)}
        </div>
      </div>

      <HPBar fraction={mon.hp_fraction ?? 1} />

      {boostEntries.length > 0 && (
        <div className="stat-boosts">
          {boostEntries.map(([stat, val]) => (
            <span key={stat} className={`boost-badge ${val > 0 ? 'boost-pos' : 'boost-neg'}`}>
              {stat} {val > 0 ? `+${val}` : val}
            </span>
          ))}
        </div>
      )}

      {isOpponent && revealedMoves && revealedMoves.length > 0 && (
        <div className="revealed-moves">
          <div className="revealed-moves-title">Revealed moves</div>
          {revealedMoves.map(m => (
            <div key={m.id} className="revealed-move-item">
              · {m.id.replace(/_/g, ' ')} ({m.type}, {m.base_power} BP)
            </div>
          ))}
        </div>
      )}

      {mon.item && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.65rem', color: 'var(--text-dim)' }}>
          Item: {mon.item}
        </div>
      )}
    </div>
  )
}
