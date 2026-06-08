import { useState, useEffect } from 'react'

const QUALITY_COLOR = {
  optimal:        'var(--clr-optimal)',
  good:           'var(--clr-good)',
  suboptimal:     'var(--clr-suboptimal)',
  fallback:       'var(--clr-fallback)',
  switch:         'var(--clr-switch)',
  good_switch:    'var(--clr-good)',
  bad_switch:     'var(--clr-suboptimal)',
  neutral_switch: 'var(--clr-switch)',
  forced_switch:  'rgba(120,120,140,0.7)',
  no_data:        'var(--clr-no-data)',
}

const QUALITY_LABEL = {
  optimal:        'OPTIMAL',
  good:           'GOOD',
  suboptimal:     'SUBOPTIMAL',
  fallback:       'FALLBACK',
  switch:         'SWITCH',
  good_switch:    'GOOD SWITCH',
  bad_switch:     'BAD SWITCH',
  neutral_switch: 'SWITCH',
  forced_switch:  'FORCED',
  no_data:        '—',
}

const RNG_ICON = {
  possible_crit: { icon: '⚡', label: 'CRIT?', cls: 'rng-crit' },
  possible_miss: { icon: '✕',  label: 'MISS?', cls: 'rng-miss' },
}


// ---------------------------------------------------------------------------
// Battle narrative ("Battle Story")
// ---------------------------------------------------------------------------

function BattleStory({ narrative }) {
  if (!narrative) return null
  return (
    <div className="battle-story">
      <div className="battle-story-title">📖 BATTLE STORY</div>
      <p className="battle-story-text">{narrative}</p>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Variance report (crits / misses)
// ---------------------------------------------------------------------------

function VarianceReport({ report, p1Label, p2Label }) {
  if (!report || report.total_events === 0) return null

  const { crits = [], misses = [], verdict = '' } = report
  const verdictClass = verdict.toLowerCase().includes('heavily')
    ? 'variance-heavy'
    : verdict.toLowerCase().includes('some')
      ? 'variance-some'
      : 'variance-minimal'

  return (
    <div className={`variance-panel ${verdictClass}`}>
      <div className="variance-title">🎲 RNG REPORT</div>
      <div className="variance-verdict">{verdict}</div>
      {crits.length > 0 && (
        <div className="variance-row">
          <span className="rng-crit">⚡ POSSIBLE CRITS</span>
          {crits.map((c, i) => (
            <span key={i} className="variance-event">
              T{c.turn_number} {c.player_role === 'p1' ? p1Label : p2Label}
            </span>
          ))}
        </div>
      )}
      {misses.length > 0 && (
        <div className="variance-row">
          <span className="rng-miss">✕ POSSIBLE MISSES</span>
          {misses.map((m, i) => (
            <span key={i} className="variance-event">
              T{m.turn_number} {m.player_role === 'p1' ? p1Label : p2Label}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Decision quality stacked bar
// ---------------------------------------------------------------------------

function QualityBar({ summary }) {
  const total = (summary.optimal || 0) + (summary.good || 0) +
                (summary.suboptimal || 0) + (summary.fallback || 0)
  if (total === 0) return <div className="quality-bar-empty">No turn data</div>

  const segments = [
    { key: 'optimal',    count: summary.optimal    || 0 },
    { key: 'good',       count: summary.good       || 0 },
    { key: 'suboptimal', count: summary.suboptimal || 0 },
    { key: 'fallback',   count: summary.fallback   || 0 },
  ].filter(s => s.count > 0)

  // Switch quality breakdown (new — may be absent in older analyses)
  const goodSwitches    = summary.good_switches    || 0
  const badSwitches     = summary.bad_switches     || 0
  const neutralSwitches = summary.neutral_switches || 0
  const forcedSwitches  = summary.forced_switches  || 0
  const hasDetailedSwitches = goodSwitches + badSwitches + neutralSwitches + forcedSwitches > 0

  return (
    <div className="quality-bar-wrap">
      <div className="quality-bar">
        {segments.map(s => (
          <div
            key={s.key}
            className="quality-segment"
            style={{
              width: `${(s.count / total) * 100}%`,
              background: QUALITY_COLOR[s.key],
            }}
            title={`${QUALITY_LABEL[s.key]}: ${s.count}`}
          />
        ))}
      </div>
      <div className="quality-legend">
        {segments.map(s => (
          <span key={s.key} className="legend-item">
            <span className="legend-dot" style={{ background: QUALITY_COLOR[s.key] }} />
            {s.count} {QUALITY_LABEL[s.key]}
          </span>
        ))}
        {!hasDetailedSwitches && summary.switch_turns > 0 && (
          <span className="legend-item">
            <span className="legend-dot" style={{ background: QUALITY_COLOR.switch }} />
            {summary.switch_turns} SWITCH
          </span>
        )}
        {hasDetailedSwitches && (
          <>
            {goodSwitches > 0 && (
              <span className="legend-item">
                <span className="legend-dot" style={{ background: QUALITY_COLOR.good_switch }} />
                {goodSwitches} GOOD SW
              </span>
            )}
            {badSwitches > 0 && (
              <span className="legend-item">
                <span className="legend-dot" style={{ background: QUALITY_COLOR.bad_switch }} />
                {badSwitches} BAD SW
              </span>
            )}
            {neutralSwitches > 0 && (
              <span className="legend-item">
                <span className="legend-dot" style={{ background: QUALITY_COLOR.neutral_switch }} />
                {neutralSwitches} SW
              </span>
            )}
            {forcedSwitches > 0 && (
              <span className="legend-item">
                <span className="legend-dot" style={{ background: QUALITY_COLOR.forced_switch }} />
                {forcedSwitches} FORCED
              </span>
            )}
          </>
        )}
        {summary.blunders > 0 && (
          <span className="legend-item legend-blunders">
            ⚠ {summary.blunders} BLUNDER{summary.blunders > 1 ? 'S' : ''}
          </span>
        )}
        {summary.decision_quality_pct != null && (
          <span className="legend-quality-pct">
            {summary.decision_quality_pct}% quality
          </span>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Win probability sparkline SVG (Wave 2C)
// ---------------------------------------------------------------------------

function WinProbSparkline({ timeline, turningPoint, p1Label, p2Label }) {
  if (!timeline || timeline.length < 2) return null

  const valid = timeline.filter(t => t.p1_win_prob != null)
  if (valid.length < 2) return null

  const W = 1000
  const H = 48

  const xOf = (i) => (i / (valid.length - 1)) * W
  const yOf = (prob) => H - prob * H

  const pts = valid.map((t, i) => `${xOf(i).toFixed(1)},${yOf(t.p1_win_prob).toFixed(1)}`).join(' L ')
  const path = `M ${pts}`

  // Turning point marker
  const tpIdx = turningPoint != null
    ? valid.findIndex(t => t.turn_number === turningPoint)
    : -1

  // Shaded area under the curve (P1 advantage zone, above 50%)
  const areaTop = valid.map((t, i) => `${xOf(i).toFixed(1)},${yOf(t.p1_win_prob).toFixed(1)}`).join(' L ')
  const areaPath = `M 0,${H / 2} L ${areaTop} L ${xOf(valid.length - 1).toFixed(1)},${H / 2} Z`

  return (
    <div className="winprob-sparkline">
      <div className="winprob-labels">
        <span className="wp-p1">■ {p1Label}</span>
        <span className="wp-center">WIN PROBABILITY</span>
        <span className="wp-p2">{p2Label} ■</span>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="wp-svg">
        {/* 50% midline */}
        <line x1="0" y1={H / 2} x2={W} y2={H / 2}
          stroke="rgba(255,255,255,0.12)" strokeDasharray="5 4" />

        {/* Shaded advantage area */}
        <path d={areaPath} fill="rgba(0,230,255,0.06)" />

        {/* Main win prob line */}
        <path d={path} fill="none"
          stroke="rgba(0,230,255,0.7)" strokeWidth="1.5"
          strokeLinecap="round" strokeLinejoin="round" />

        {/* Turning point marker */}
        {tpIdx >= 0 && (
          <>
            <line
              x1={xOf(tpIdx)} y1="0"
              x2={xOf(tpIdx)} y2={H}
              stroke="var(--accent-amber)" strokeWidth="1"
              strokeDasharray="3 3" opacity="0.8"
            />
            <circle
              cx={xOf(tpIdx)}
              cy={yOf(valid[tpIdx].p1_win_prob)}
              r="4" fill="var(--accent-amber)"
            />
          </>
        )}
      </svg>
      {tpIdx >= 0 && (
        <div className="wp-turning-point">
          ⚡ Largest swing at turn {valid[tpIdx].turn_number}
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Blunders list (Wave 2C)
// ---------------------------------------------------------------------------

function BlundersList({ blunders, p1Label, p2Label }) {
  if (!blunders || blunders.length === 0) return null

  return (
    <div className="blunders-panel">
      <div className="blunders-title">⚠ BLUNDERS ({blunders.length})</div>
      {blunders.map((b, i) => {
        const label = b.player_role === 'p1' ? p1Label : p2Label
        const gapPct = b.score_gap != null ? `${Math.round(b.score_gap * 100)}% below best` : ''
        return (
          <div key={i} className="blunder-row">
            <span className={`blunder-player ${b.player_role}`}>{label}</span>
            <span className="blunder-turn">T{b.turn_number}</span>
            <span className="blunder-gap">{gapPct}</span>
            <span className="blunder-note">{b.notes}</span>
          </div>
        )
      })}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Turn log
// ---------------------------------------------------------------------------

function TurnList({ turns }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? turns : turns.slice(0, 6)

  return (
    <div className="turn-list">
      <div className="turn-list-header" onClick={() => setExpanded(e => !e)}>
        <span>TURN LOG ({turns.length} turns)</span>
        <span className="turn-expand-icon">{expanded ? '▲' : '▼'}</span>
      </div>
      {visible.map((t, i) => {
        const rng = t.rng_flag ? RNG_ICON[t.rng_flag] : null
        return (
          <div key={i} className={`turn-row${t.is_blunder ? ' turn-row-blunder' : ''}`}>
            <span className="turn-num">T{t.turn_number}</span>
            <span className="turn-role">{t.player_role.toUpperCase()}</span>
            <span
              className="turn-quality-badge"
              style={{ background: QUALITY_COLOR[t.decision_quality] }}
            >
              {QUALITY_LABEL[t.decision_quality]}
            </span>
            {t.is_blunder && <span className="turn-blunder-tag">⚠</span>}
            {rng && (
              <span className={`turn-rng-badge ${rng.cls}`} title={rng.label}>
                {rng.icon}
              </span>
            )}
            <span className="turn-action">{t.action_chosen || '—'}</span>
            {t.notes && <span className="turn-notes">{t.notes}</span>}
          </div>
        )
      })}
      {!expanded && turns.length > 6 && (
        <div className="turn-show-more" onClick={() => setExpanded(true)}>
          Show {turns.length - 6} more turns ▼
        </div>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main BattleAnalysis
// ---------------------------------------------------------------------------

export default function BattleAnalysis({ battleId, p1Label, p2Label }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]     = useState(null)

  const p1 = p1Label ?? 'P1'
  const p2 = p2Label ?? 'P2'

  useEffect(() => {
    if (!battleId) return
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      try {
        const r = await fetch(`/api/battles/${battleId}/analysis`)
        if (!r.ok) throw new Error(r.statusText)
        const json = await r.json()
        if (!cancelled) setData(json)
      } catch(e) {
        if (!cancelled) setError(String(e))
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [battleId])

  if (loading) return <div className="analysis-loading">Analyzing…</div>
  if (error)   return <div className="analysis-error">Analysis failed: {error}</div>
  if (!data)   return null

  const {
    p1_summary, p2_summary, turns,
    win_probability_timeline, turning_point,
    blunders, narrative, variance_report,
  } = data
  const hasTurnData = turns.some(t => t.decision_quality !== 'no_data')

  return (
    <div className="analysis-panel">

      {/* Battle narrative */}
      <BattleStory narrative={narrative} />

      {/* Win probability sparkline */}
      {win_probability_timeline?.length >= 2 && (
        <WinProbSparkline
          timeline={win_probability_timeline}
          turningPoint={turning_point}
          p1Label={p1}
          p2Label={p2}
        />
      )}

      {/* Variance / RNG report */}
      <VarianceReport report={variance_report} p1Label={p1} p2Label={p2} />

      {/* Decision quality bars */}
      <div className="analysis-summaries">
        <div className="analysis-player-card">
          <div className="analysis-player-label p1">{p1}</div>
          <div className="analysis-stat-row">
            <span>{p1_summary.total_turns} turns</span>
            {p1_summary.avg_heuristic_rank != null && (
              <span>avg rank {p1_summary.avg_heuristic_rank}</span>
            )}
          </div>
          <QualityBar summary={p1_summary} />
        </div>
        <div className="analysis-player-card">
          <div className="analysis-player-label p2">{p2}</div>
          <div className="analysis-stat-row">
            <span>{p2_summary.total_turns} turns</span>
            {p2_summary.avg_heuristic_rank != null && (
              <span>avg rank {p2_summary.avg_heuristic_rank}</span>
            )}
          </div>
          <QualityBar summary={p2_summary} />
        </div>
      </div>

      {/* Blunders */}
      <BlundersList blunders={blunders} p1Label={p1} p2Label={p2} />

      {/* Turn-by-turn log */}
      {hasTurnData
        ? <TurnList turns={turns} />
        : <div className="analysis-no-data">No turn state captured — run a battle with an LLM player to see analysis.</div>
      }
    </div>
  )
}
