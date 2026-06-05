import HPBar from './HPBar'

// Official Pokémon type colours
const TYPE_COLORS = {
  NORMAL: '#9a9a7a', FIRE: '#ff6b35', WATER: '#4d9de0', ELECTRIC: '#f7c948',
  GRASS: '#4caf50', ICE: '#80deea', FIGHTING: '#e53935', POISON: '#ab47bc',
  GROUND: '#c6a34a', FLYING: '#9575cd', PSYCHIC: '#e91e8c', BUG: '#8bc34a',
  ROCK: '#a1887f', GHOST: '#5e35b1', DRAGON: '#5c6bc0', DARK: '#6d4c41',
  STEEL: '#90a4ae', FAIRY: '#f48fb1',
}

/**
 * Convert a species name to a Showdown Gen 3 sprite URL.
 * Showdown uses lowercase, hyphens for spaces, and handles most forms.
 */
function spriteUrl(species) {
  if (!species) return null
  const slug = species.toLowerCase().replace(/[^a-z0-9]/g, '').replace(/\s+/g, '-')
  return `https://play.pokemonshowdown.com/sprites/gen3/${slug}.png`
}

function PokemonSprite({ species, size = 80, isThinking = false }) {
  const url = spriteUrl(species)
  if (!url) return null
  return (
    <div
      className={`pokemon-sprite-wrap${isThinking ? ' thinking' : ''}`}
      style={{ width: size, height: size }}
    >
      <img
        className="pokemon-sprite"
        src={url}
        alt={species}
        width={size}
        height={size}
        onError={e => { e.currentTarget.style.display = 'none' }}
        style={{ imageRendering: 'pixelated' }}
      />
      {isThinking && (
        <div className="thinking-dots">
          <span /><span /><span />
        </div>
      )}
    </div>
  )
}

function TypeBadge({ type }) {
  const color = TYPE_COLORS[type] || '#666'
  return (
    <span className="type-badge" style={{ background: color }}>
      {type}
    </span>
  )
}

function StatusBadge({ status }) {
  if (!status) return null
  const short = {
    BURNED: 'BRN', PARALYZED: 'PAR', POISONED: 'PSN',
    TOXIC: 'TOX', ASLEEP: 'SLP', FROZEN: 'FRZ', FAINTED: 'FNT',
  }
  const label = short[status] || status.slice(0, 3)
  return <span className={`status-badge status-${label}`}>{label}</span>
}

/** Mini reserve-mon shown on the bench row */
function BenchSlot({ mon }) {
  if (!mon) return <div className="bench-slot empty" />
  const url = spriteUrl(mon.species)
  return (
    <div
      className={`bench-slot${mon.fainted ? ' fainted' : ''}`}
      title={`${mon.species} — ${Math.round((mon.hp_fraction ?? 0) * 100)}% HP${mon.status ? ` [${mon.status}]` : ''}`}
    >
      {url ? (
        <img
          src={url}
          alt={mon.species}
          className="bench-sprite"
          onError={e => { e.currentTarget.style.display = 'none' }}
          style={{ imageRendering: 'pixelated' }}
        />
      ) : (
        <div className="bench-sprite-fallback">{mon.species?.slice(0, 2).toUpperCase()}</div>
      )}
      <div
        className="bench-hp-bar"
        style={{
          '--hp': `${Math.round((mon.hp_fraction ?? 0) * 100)}%`,
          '--hp-color': (mon.hp_fraction ?? 0) > 0.5 ? '#4caf50'
            : (mon.hp_fraction ?? 0) > 0.2 ? '#f7c948' : '#ff4455',
        }}
      />
    </div>
  )
}

export default function PokemonCard({ mon, side, isOpponent = false, isThinking = false, bench = [] }) {
  if (!mon) {
    return (
      <div className={`pokemon-card ${side} empty`}>
        <div className="card-empty-label">waiting…</div>
        {isThinking && (
          <div className="thinking-dots standalone">
            <span /><span /><span />
          </div>
        )}
      </div>
    )
  }

  const boostEntries = Object.entries(mon.boosts || {}).filter(([, v]) => v !== 0)
  const revealedMoves = isOpponent ? Object.values(mon.revealed_moves || {}) : null

  return (
    <div className={`pokemon-card ${side}${isThinking ? ' is-thinking' : ''}`}>
      {/* Sprite */}
      <PokemonSprite species={mon.species} size={88} isThinking={isThinking} />

      <div className="card-body">
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
          <div className="mon-item">Item: {mon.item}</div>
        )}
      </div>

      {/* Reserve bench */}
      {bench.length > 0 && (
        <div className="bench-row">
          {bench.map((b, i) => <BenchSlot key={i} mon={b} />)}
        </div>
      )}
    </div>
  )
}
