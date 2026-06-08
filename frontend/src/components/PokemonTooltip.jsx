/**
 * PokemonTooltip — hover overlay showing base stats, type matchups, ability, and item.
 *
 * Usage:
 *   const tooltip = useTooltip()
 *   <div onMouseEnter={tooltip.onEnter} onMouseLeave={tooltip.onLeave}>…</div>
 *   <PokemonTooltip mon={mon} anchor={tooltip.anchor} />
 *
 * useTooltip is in hooks/useTooltip.js.
 */

import { createPortal } from 'react-dom'

// ---------------------------------------------------------------------------
// Gen 3 type chart (attacking type → {defending type: multiplier})
// Only non-1× values are stored; everything else is implicitly 1×.
// ---------------------------------------------------------------------------

const CHART = {
  NORMAL:   { ROCK: 0.5, GHOST: 0,   STEEL: 0.5 },
  FIRE:     { FIRE: 0.5, WATER: 0.5, ROCK: 0.5,  DRAGON: 0.5,
              GRASS: 2,  ICE: 2,     BUG: 2,     STEEL: 2 },
  WATER:    { WATER: 0.5, GRASS: 0.5, DRAGON: 0.5,
              FIRE: 2,   GROUND: 2,  ROCK: 2 },
  ELECTRIC: { ELECTRIC: 0.5, GRASS: 0.5, DRAGON: 0.5,
              GROUND: 0, FLYING: 2,  WATER: 2 },
  GRASS:    { FIRE: 0.5, GRASS: 0.5, POISON: 0.5, FLYING: 0.5,
              BUG: 0.5,  DRAGON: 0.5, STEEL: 0.5,
              WATER: 2,  GROUND: 2,  ROCK: 2 },
  ICE:      { WATER: 0.5, ICE: 0.5,
              GRASS: 2,  GROUND: 2,  FLYING: 2,  DRAGON: 2 },
  FIGHTING: { POISON: 0.5, BUG: 0.5, FLYING: 0.5, PSYCHIC: 0.5, GHOST: 0,
              NORMAL: 2,  ICE: 2,    ROCK: 2,    DARK: 2,   STEEL: 2 },
  POISON:   { POISON: 0.5, GROUND: 0.5, ROCK: 0.5, GHOST: 0.5, STEEL: 0,
              GRASS: 2 },
  GROUND:   { GRASS: 0.5, BUG: 0.5, FLYING: 0,
              FIRE: 2,   ELECTRIC: 2, POISON: 2, ROCK: 2,   STEEL: 2 },
  FLYING:   { ELECTRIC: 0.5, ROCK: 0.5, STEEL: 0.5,
              GRASS: 2,  FIGHTING: 2, BUG: 2 },
  PSYCHIC:  { PSYCHIC: 0.5, STEEL: 0.5, DARK: 0,
              FIGHTING: 2, POISON: 2 },
  BUG:      { FIRE: 0.5, FIGHTING: 0.5, FLYING: 0.5, GHOST: 0.5,
              STEEL: 0.5, POISON: 0.5,
              GRASS: 2,  PSYCHIC: 2, DARK: 2 },
  ROCK:     { FIGHTING: 0.5, GROUND: 0.5, STEEL: 0.5,
              FIRE: 2,   ICE: 2,    FLYING: 2,  BUG: 2 },
  GHOST:    { DARK: 0.5, NORMAL: 0,
              GHOST: 2,  PSYCHIC: 2 },
  DRAGON:   { STEEL: 0.5,
              DRAGON: 2 },
  DARK:     { FIGHTING: 0.5, DARK: 0.5, STEEL: 0.5,
              GHOST: 2,  PSYCHIC: 2 },
  STEEL:    { FIRE: 0.5, WATER: 0.5, ELECTRIC: 0.5, STEEL: 0.5,
              ICE: 2,    ROCK: 2 },
}

const ALL_TYPES = Object.keys(CHART)

function effectiveness(attackingType, defendingTypes) {
  return defendingTypes.reduce((mult, dt) => mult * (CHART[attackingType]?.[dt] ?? 1), 1)
}

function computeMatchups(types) {
  const groups = { immune: [], quarter: [], half: [], double: [], quad: [] }
  for (const at of ALL_TYPES) {
    const m = effectiveness(at, types)
    if (m === 0)         groups.immune.push(at)
    else if (m === 0.25) groups.quarter.push(at)
    else if (m === 0.5)  groups.half.push(at)
    else if (m === 2)    groups.double.push(at)
    else if (m >= 4)     groups.quad.push(at)
  }
  return groups
}

// ---------------------------------------------------------------------------
// Type / stat colours
// ---------------------------------------------------------------------------

const TYPE_COLORS = {
  NORMAL: '#9a9a7a', FIRE: '#ff6b35', WATER: '#4d9de0', ELECTRIC: '#f7c948',
  GRASS: '#4caf50', ICE: '#80deea', FIGHTING: '#e53935', POISON: '#ab47bc',
  GROUND: '#c6a34a', FLYING: '#9575cd', PSYCHIC: '#e91e8c', BUG: '#8bc34a',
  ROCK: '#a1887f', GHOST: '#5e35b1', DRAGON: '#5c6bc0', DARK: '#6d4c41',
  STEEL: '#90a4ae',
}

const STAT_META = {
  hp:  { label: 'HP',  color: '#e53935' },
  atk: { label: 'Atk', color: '#ff9800' },
  def: { label: 'Def', color: '#fdd835' },
  spa: { label: 'SpA', color: '#42a5f5' },
  spd: { label: 'SpD', color: '#26c6da' },
  spe: { label: 'Spe', color: '#ab47bc' },
}
const STAT_ORDER = ['hp', 'atk', 'def', 'spa', 'spd', 'spe']
const STAT_SCALE = 180

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function StatBar({ statKey, value }) {
  const meta = STAT_META[statKey]
  if (!meta) return null
  const pct = Math.min(100, Math.round((value / STAT_SCALE) * 100))
  return (
    <div className="tt-stat-row">
      <span className="tt-stat-label">{meta.label}</span>
      <div className="tt-stat-track">
        <div className="tt-stat-bar" style={{ width: `${pct}%`, background: meta.color }} />
      </div>
      <span className="tt-stat-value" style={{ color: meta.color }}>{value}</span>
    </div>
  )
}

function TypePill({ type, modifier }) {
  const color = TYPE_COLORS[type] ?? '#666'
  return (
    <span className="tt-type-pill" style={{ background: color }} title={`${type} — ${modifier}`}>
      {type}
    </span>
  )
}

function MatchupSection({ types }) {
  const groups = computeMatchups(types)
  const rows = [
    { label: '4×', key: 'quad',    cls: 'tt-weak-quad'      },
    { label: '2×', key: 'double',  cls: 'tt-weak-double'    },
    { label: '½',  key: 'half',    cls: 'tt-resist-half'    },
    { label: '¼',  key: 'quarter', cls: 'tt-resist-quarter' },
    { label: '0×', key: 'immune',  cls: 'tt-immune'         },
  ]
  const hasAny = rows.some(r => groups[r.key].length > 0)
  if (!hasAny) return null
  return (
    <div className="tt-section">
      <div className="tt-section-title">TYPE MATCHUPS</div>
      {rows.map(({ label, key, cls }) =>
        groups[key].length > 0 ? (
          <div key={key} className="tt-matchup-row">
            <span className={`tt-mult-label ${cls}`}>{label}</span>
            <div className="tt-matchup-pills">
              {groups[key].map(t => <TypePill key={t} type={t} modifier={label} />)}
            </div>
          </div>
        ) : null
      )}
    </div>
  )
}

function TooltipContent({ mon }) {
  const stats   = mon?.base_stats
  const types   = mon?.types ?? []
  const ability = mon?.ability
  const item    = mon?.item

  return (
    <div className="tt-inner">
      <div className="tt-header">
        <span className="tt-species">{mon?.species}</span>
        <div className="tt-type-badges">
          {types.map(t => (
            <span key={t} className="tt-header-type" style={{ background: TYPE_COLORS[t] ?? '#666' }}>
              {t}
            </span>
          ))}
        </div>
      </div>

      {stats && Object.keys(stats).length > 0 && (
        <div className="tt-section">
          <div className="tt-section-title">BASE STATS</div>
          {STAT_ORDER.map(k => stats[k] != null
            ? <StatBar key={k} statKey={k} value={stats[k]} />
            : null
          )}
        </div>
      )}

      <MatchupSection types={types} />

      {(ability || item) && (
        <div className="tt-section tt-detail-row">
          {ability && (
            <span className="tt-detail">
              <span className="tt-detail-label">ABL</span>
              {ability.replace(/_/g, ' ')}
            </span>
          )}
          {item && (
            <span className="tt-detail">
              <span className="tt-detail-label">ITEM</span>
              {item.replace(/_/g, ' ')}
            </span>
          )}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Portal
// ---------------------------------------------------------------------------

const TOOLTIP_WIDTH = 230
const EDGE_PAD = 12

function positionTooltip(rect, winW, winH) {
  let x = rect.right + 10
  let y = rect.top
  if (x + TOOLTIP_WIDTH > winW - EDGE_PAD) x = rect.left - TOOLTIP_WIDTH - 10
  const maxY = winH - 320 - EDGE_PAD
  if (y > maxY) y = maxY
  if (y < EDGE_PAD) y = EDGE_PAD
  return { x, y }
}

export default function PokemonTooltip({ mon, anchor }) {
  if (!anchor || !mon) return null
  const { x, y } = positionTooltip(anchor, window.innerWidth, window.innerHeight)
  return createPortal(
    <div
      className="pokemon-tooltip"
      style={{ left: x, top: y, width: TOOLTIP_WIDTH }}
      onMouseEnter={e => e.stopPropagation()}
    >
      <TooltipContent mon={mon} />
    </div>,
    document.body
  )
}
