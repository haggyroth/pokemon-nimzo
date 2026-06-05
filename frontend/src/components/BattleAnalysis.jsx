import { useState, useEffect } from 'react'

const QUALITY_COLOR = {
  optimal:    'var(--clr-optimal)',
  good:       'var(--clr-good)',
  suboptimal: 'var(--clr-suboptimal)',
  fallback:   'var(--clr-fallback)',
  switch:     'var(--clr-switch)',
  no_data:    'var(--clr-no-data)',
}

const QUALITY_LABEL = {
  optimal:    'OPTIMAL',
  good:       'GOOD',
  suboptimal: 'SUBOPTIMAL',
  fallback:   'FALLBACK',
  switch:     'SWITCH',
  no_data:    '—',
}

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
        {summary.switch_turns > 0 && (
          <span className="legend-item">
            <span className="legend-dot" style={{ background: QUALITY_COLOR.switch }} />
            {summary.switch_turns} SWITCH
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

function TurnList({ turns }) {
  const [expanded, setExpanded] = useState(false)
  const visible = expanded ? turns : turns.slice(0, 6)

  return (
    <div className="turn-list">
      <div className="turn-list-header" onClick={() => setExpanded(e => !e)}>
        <span>TURN LOG ({turns.length} turns)</span>
        <span className="turn-expand-icon">{expanded ? '▲' : '▼'}</span>
      </div>
      {visible.map((t, i) => (
        <div key={i} className="turn-row">
          <span className="turn-num">T{t.turn_number}</span>
          <span className="turn-role">{t.player_role.toUpperCase()}</span>
          <span
            className="turn-quality-badge"
            style={{ background: QUALITY_COLOR[t.decision_quality] }}
          >
            {QUALITY_LABEL[t.decision_quality]}
          </span>
          <span className="turn-action">{t.action_chosen || '—'}</span>
          {t.notes && <span className="turn-notes">{t.notes}</span>}
        </div>
      ))}
      {!expanded && turns.length > 6 && (
        <div className="turn-show-more" onClick={() => setExpanded(true)}>
          Show {turns.length - 6} more turns ▼
        </div>
      )}
    </div>
  )
}

export default function BattleAnalysis({ battleId }) {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)

  useEffect(() => {
    if (!battleId) return
    setLoading(true)
    setError(null)
    fetch(`/api/battles/${battleId}/analysis`)
      .then(r => r.ok ? r.json() : Promise.reject(r.statusText))
      .then(setData)
      .catch(e => setError(String(e)))
      .finally(() => setLoading(false))
  }, [battleId])

  if (loading) return <div className="analysis-loading">Analyzing…</div>
  if (error)   return <div className="analysis-error">Analysis failed: {error}</div>
  if (!data)   return null

  const { p1_summary, p2_summary, turns } = data
  const hasTurnData = turns.some(t => t.decision_quality !== 'no_data')

  return (
    <div className="analysis-panel">
      <div className="analysis-summaries">
        <div className="analysis-player-card">
          <div className="analysis-player-label">P1</div>
          <div className="analysis-stat-row">
            <span>{p1_summary.total_turns} turns</span>
            {p1_summary.avg_heuristic_rank != null && (
              <span>avg rank {p1_summary.avg_heuristic_rank}</span>
            )}
          </div>
          <QualityBar summary={p1_summary} />
        </div>
        <div className="analysis-player-card">
          <div className="analysis-player-label">P2</div>
          <div className="analysis-stat-row">
            <span>{p2_summary.total_turns} turns</span>
            {p2_summary.avg_heuristic_rank != null && (
              <span>avg rank {p2_summary.avg_heuristic_rank}</span>
            )}
          </div>
          <QualityBar summary={p2_summary} />
        </div>
      </div>

      {hasTurnData
        ? <TurnList turns={turns} />
        : <div className="analysis-no-data">No turn state captured — run a battle with an LLM player to see analysis.</div>
      }
    </div>
  )
}
