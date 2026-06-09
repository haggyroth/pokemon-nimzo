import { useEffect, useReducer } from 'react'

// ---------------------------------------------------------------------------
// Sprite helper (same CDN as PokemonCard)
// ---------------------------------------------------------------------------

function spriteUrl(species) {
  if (!species) return null
  const id = species.toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-]/g, '')
  return `https://play.pokemonshowdown.com/sprites/home/${id}.png`
}

// ---------------------------------------------------------------------------
// Tier label map
// ---------------------------------------------------------------------------

const TIER_LABELS = {
  random: 'RANDOM', ou: 'OU', ubers: 'UBERS',
  uu: 'UU', nu: 'NU', lc: 'LC', freeforall: 'FFA',
}

const TIER_COLORS = {
  random: '#4d9de0', ou: '#f7c948', ubers: '#e53935',
  uu: '#ab47bc', nu: '#4caf50', lc: '#80deea', freeforall: '#ff9800',
}

// ---------------------------------------------------------------------------
// Summary KPIs
// ---------------------------------------------------------------------------

function SummaryKpis({ summary }) {
  const { total_battles, avg_turns, decided_battles, total_models } = summary
  const decisive_pct = total_battles > 0
    ? Math.round((decided_battles / total_battles) * 100)
    : 0

  return (
    <div className="gs-kpi-row">
      <div className="gs-kpi">
        <div className="gs-kpi-value">{total_battles}</div>
        <div className="gs-kpi-label">BATTLES PLAYED</div>
      </div>
      <div className="gs-kpi">
        <div className="gs-kpi-value">{total_models}</div>
        <div className="gs-kpi-label">MODELS REGISTERED</div>
      </div>
      <div className="gs-kpi">
        <div className="gs-kpi-value">{avg_turns ?? '—'}</div>
        <div className="gs-kpi-label">AVG TURNS / BATTLE</div>
      </div>
      <div className="gs-kpi">
        <div className="gs-kpi-value">{decisive_pct}%</div>
        <div className="gs-kpi-label">DECISIVE RESULTS</div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Battles by tier — horizontal bar chart
// ---------------------------------------------------------------------------

function TierBreakdown({ battles_by_tier }) {
  if (!battles_by_tier?.length) return <div className="gs-empty">No battles recorded yet.</div>
  const max = Math.max(...battles_by_tier.map(r => r.cnt))
  return (
    <div className="gs-tier-chart">
      {battles_by_tier.map(r => {
        const pct = Math.round((r.cnt / max) * 100)
        const color = TIER_COLORS[r.tier] ?? '#666'
        return (
          <div key={r.tier} className="gs-tier-row">
            <span className="gs-tier-label" style={{ color }}>{TIER_LABELS[r.tier] ?? r.tier.toUpperCase()}</span>
            <div className="gs-tier-track">
              <div className="gs-tier-bar" style={{ width: `${pct}%`, background: color }} />
            </div>
            <span className="gs-tier-count">{r.cnt}</span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top Pokémon grid — sprite + usage bar
// ---------------------------------------------------------------------------

function TopPokemon({ top_pokemon }) {
  if (!top_pokemon?.length) return <div className="gs-empty">No turn data recorded yet.</div>
  const max = top_pokemon[0]?.cnt ?? 1
  return (
    <div className="gs-pokemon-grid">
      {top_pokemon.map((r, i) => {
        const url = spriteUrl(r.species)
        const pct = Math.round((r.cnt / max) * 100)
        return (
          <div key={r.species} className="gs-pokemon-card">
            <span className="gs-pokemon-rank">#{i + 1}</span>
            {url && (
              <img
                src={url}
                alt={r.species}
                className="gs-pokemon-sprite"
                onError={e => { e.currentTarget.style.display = 'none' }}
                style={{ imageRendering: 'pixelated' }}
              />
            )}
            <div className="gs-pokemon-name">{r.species}</div>
            <div className="gs-pokemon-track">
              <div className="gs-pokemon-bar" style={{ width: `${pct}%` }} />
            </div>
            <div className="gs-pokemon-cnt">{r.cnt} turns</div>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Top moves — ranked list
// ---------------------------------------------------------------------------

function TopMoves({ top_moves }) {
  if (!top_moves?.length) return <div className="gs-empty">No move data recorded yet.</div>
  const max = top_moves[0]?.cnt ?? 1
  return (
    <div className="gs-move-list">
      {top_moves.map((r, i) => {
        const pct = Math.round((r.cnt / max) * 100)
        return (
          <div key={r.move ?? i} className="gs-move-row">
            <span className="gs-move-rank">#{i + 1}</span>
            <span className="gs-move-name">{(r.move ?? 'unknown').replace(/_/g, ' ')}</span>
            <div className="gs-move-track">
              <div className="gs-move-bar" style={{ width: `${pct}%` }} />
            </div>
            <span className="gs-move-cnt">{r.cnt}</span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Recent battles feed
// ---------------------------------------------------------------------------

function RecentBattles({ recent_battles, onReplaySelected }) {
  if (!recent_battles?.length) return <div className="gs-empty">No battles recorded yet.</div>
  return (
    <div className="gs-recent-list">
      {recent_battles.map(b => {
        const result = b.winner === 1 ? 'p1' : b.winner === 2 ? 'p2' : 'tie'
        const tierColor = TIER_COLORS[b.tier] ?? '#666'
        const tierLabel = TIER_LABELS[b.tier] ?? b.tier?.toUpperCase()
        return (
          <div key={b.id} className="gs-recent-row">
            <span className="gs-recent-tier" style={{ color: tierColor }}>{tierLabel}</span>
            <div className="gs-recent-matchup">
              <span className={result === 'p1' ? 'gs-winner' : ''}>{b.p1?.split('/').pop()}</span>
              <span className="gs-vs">vs</span>
              <span className={result === 'p2' ? 'gs-winner' : ''}>{b.p2?.split('/').pop()}</span>
            </div>
            <span className="gs-recent-turns">{b.total_turns ?? '?'}t</span>
            <span className="gs-recent-date">
              {b.finished_at ? new Date(b.finished_at).toLocaleDateString() : '—'}
            </span>
            {onReplaySelected && (
              <button
                className="btn-replay btn-replay-sm"
                onClick={() => onReplaySelected(b.id)}
                title="Watch replay"
              >▶</button>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Fetch reducer
// ---------------------------------------------------------------------------

function reducer(state, action) {
  switch (action.type) {
    case 'start':   return { loading: true,  error: null,         data: null }
    case 'success': return { loading: false, error: null,         data: action.data }
    case 'error':   return { loading: false, error: action.error, data: null }
    default:        return state
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

export default function GlobalStats({ onClose, onReplaySelected }) {
  const [{ loading, error, data }, dispatch] = useReducer(
    reducer,
    { loading: true, error: null, data: null },
  )

  useEffect(() => {
    let cancelled = false
    dispatch({ type: 'start' })
    fetch('/api/stats/global')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(d => { if (!cancelled) dispatch({ type: 'success', data: d }) })
      .catch(e => { if (!cancelled) dispatch({ type: 'error', error: e.message }) })
    return () => { cancelled = true }
  }, [])

  if (loading) return (
    <div className="stats-page">
      <div className="stats-loading">Loading global stats…</div>
    </div>
  )
  if (error || !data) return (
    <div className="stats-page">
      <button className="stats-back" onClick={onClose}>← BACK</button>
      <div className="stats-error">Failed to load stats: {error}</div>
    </div>
  )

  const { summary, battles_by_tier, top_pokemon, top_moves, recent_battles } = data

  return (
    <div className="stats-page">
      <div className="stats-header">
        <button className="stats-back" onClick={onClose}>← BACK</button>
        <div className="stats-identity">
          <div className="stats-model-name">GLOBAL STATS</div>
          <div className="stats-provider-row">
            <span className="provider-tag">all models · all battles</span>
          </div>
        </div>
      </div>

      {/* Summary KPIs */}
      <div className="panel stats-panel gs-summary-panel">
        <SummaryKpis summary={summary} />
      </div>

      {/* Two-column: Tier breakdown + Recent battles */}
      <div className="stats-grid">
        <div className="panel stats-panel">
          <div className="panel-title">BATTLES BY TIER</div>
          <TierBreakdown battles_by_tier={battles_by_tier} />
        </div>
        <div className="panel stats-panel">
          <div className="panel-title">RECENT BATTLES</div>
          <RecentBattles recent_battles={recent_battles} onReplaySelected={onReplaySelected} />
        </div>
      </div>

      {/* Top Pokémon */}
      <div className="panel stats-panel">
        <div className="panel-title">
          TOP POKÉMON
          <span className="panel-subtitle">by active turns across all battles</span>
        </div>
        <TopPokemon top_pokemon={top_pokemon} />
      </div>

      {/* Top Moves */}
      <div className="panel stats-panel">
        <div className="panel-title">
          TOP MOVES
          <span className="panel-subtitle">most chosen across all models</span>
        </div>
        <TopMoves top_moves={top_moves} />
      </div>
    </div>
  )
}
