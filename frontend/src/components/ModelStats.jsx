import { useState, useEffect } from 'react'

// ---------------------------------------------------------------------------
// ELO Sparkline — pure SVG, no external deps
// ---------------------------------------------------------------------------

function EloSparkline({ history }) {
  if (!history || history.length < 2) {
    return (
      <div className="sparkline-empty">Not enough data for ELO chart</div>
    )
  }

  const W = 560
  const H = 90
  const PAD = { top: 12, right: 16, bottom: 20, left: 48 }
  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom

  const ratings = history.map(h => h.rating_after)
  const minR = Math.min(...ratings)
  const maxR = Math.max(...ratings)
  const range = maxR - minR || 1

  const xOf = i => PAD.left + (i / (history.length - 1)) * innerW
  const yOf = r => PAD.top + innerH - ((r - minR) / range) * innerH

  const pts = history.map((h, i) => `${xOf(i)},${yOf(h.rating_after)}`).join(' ')
  const areaPts = [
    `${PAD.left},${PAD.top + innerH}`,
    ...history.map((h, i) => `${xOf(i)},${yOf(h.rating_after)}`),
    `${xOf(history.length - 1)},${PAD.top + innerH}`,
  ].join(' ')

  // Y-axis labels
  const yTicks = [minR, (minR + maxR) / 2, maxR]

  const lastRating = ratings[ratings.length - 1]
  const firstRating = ratings[0]
  const delta = lastRating - firstRating
  const deltaSign = delta >= 0 ? '+' : ''
  const deltaClass = delta >= 0 ? 'elo-delta-up' : 'elo-delta-down'

  return (
    <div className="sparkline-wrap">
      <div className="sparkline-header">
        <span className="sparkline-label">ELO PROGRESSION</span>
        <span className={`sparkline-delta ${deltaClass}`}>
          {deltaSign}{delta.toFixed(1)} over {history.length} battles
        </span>
      </div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="sparkline-svg"
        preserveAspectRatio="xMidYMid meet"
      >
        <defs>
          <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="var(--accent-cyan)" stopOpacity="0.25" />
            <stop offset="100%" stopColor="var(--accent-cyan)" stopOpacity="0.01" />
          </linearGradient>
        </defs>

        {/* Grid lines */}
        {yTicks.map((r, i) => (
          <g key={i}>
            <line
              x1={PAD.left} y1={yOf(r)}
              x2={PAD.left + innerW} y2={yOf(r)}
              stroke="var(--border)" strokeWidth="1" strokeDasharray="3,4"
            />
            <text
              x={PAD.left - 6} y={yOf(r) + 4}
              textAnchor="end"
              fontSize="9"
              fill="var(--text-muted)"
              fontFamily="var(--font-mono)"
            >
              {Math.round(r)}
            </text>
          </g>
        ))}

        {/* Area fill */}
        <polygon points={areaPts} fill="url(#sparkGrad)" />

        {/* Line */}
        <polyline
          points={pts}
          fill="none"
          stroke="var(--accent-cyan)"
          strokeWidth="1.8"
          strokeLinejoin="round"
          strokeLinecap="round"
        />

        {/* Data points */}
        {history.map((h, i) => (
          <circle
            key={i}
            cx={xOf(i)} cy={yOf(h.rating_after)}
            r="3"
            fill={h.delta >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}
            stroke="var(--bg-panel)"
            strokeWidth="1.5"
          />
        ))}

        {/* Start / end labels */}
        <text
          x={xOf(0)} y={yOf(firstRating) - 7}
          textAnchor="middle" fontSize="9"
          fill="var(--text-dim)" fontFamily="var(--font-mono)"
        >
          {firstRating.toFixed(0)}
        </text>
        <text
          x={xOf(history.length - 1)} y={yOf(lastRating) - 7}
          textAnchor="middle" fontSize="9"
          fill="var(--accent-cyan)" fontFamily="var(--font-mono)"
          fontWeight="600"
        >
          {lastRating.toFixed(1)}
        </text>
      </svg>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Decision quality bar
// ---------------------------------------------------------------------------

function QualityBar({ turnStats }) {
  if (!turnStats || turnStats.total_turns === 0) {
    return <div className="quality-bar-empty">No turn data recorded</div>
  }

  const { total_turns, parse_ok, parse_fail, parse_success_rate } = turnStats

  return (
    <div className="quality-section">
      <div className="quality-row">
        <span className="quality-label">Total turns logged</span>
        <span className="quality-value">{total_turns}</span>
      </div>
      <div className="quality-row">
        <span className="quality-label">Parse success rate</span>
        <span className="quality-value" style={{
          color: parse_success_rate >= 90 ? 'var(--accent-green)'
               : parse_success_rate >= 70 ? 'var(--accent-amber)'
               : 'var(--accent-red)'
        }}>
          {parse_success_rate != null ? `${parse_success_rate}%` : '—'}
        </span>
      </div>
      <div className="quality-row">
        <span className="quality-label">Valid actions / parse failures</span>
        <span className="quality-value">
          <span className="w">{parse_ok}</span>
          {' / '}
          <span className="l">{parse_fail}</span>
        </span>
      </div>

      {/* Stacked bar */}
      <div className="parse-bar-wrap">
        <div
          className="parse-bar-ok"
          style={{ width: `${parse_success_rate ?? 0}%` }}
          title={`${parse_ok} valid`}
        />
        <div
          className="parse-bar-fail"
          style={{ width: `${parse_fail / total_turns * 100}%` }}
          title={`${parse_fail} fallback`}
        />
      </div>
      <div className="parse-bar-legend">
        <span className="parse-legend-ok">■ valid action</span>
        <span className="parse-legend-fail">■ fallback (random)</span>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Battle history table
// ---------------------------------------------------------------------------

function BattleHistoryTable({ battles, onReplaySelected }) {
  if (!battles || battles.length === 0) {
    return <div className="empty-state">No completed battles yet</div>
  }

  return (
    <table className="stats-battle-table">
      <thead>
        <tr>
          <th>RESULT</th>
          <th>OPPONENT</th>
          <th>TURNS</th>
          <th>DATE</th>
          <th></th>
        </tr>
      </thead>
      <tbody>
        {battles.map(b => (
          <tr key={b.id} className={`battle-row-${b.result}`}>
            <td>
              <span className={`result-badge result-${b.result}`}>
                {b.result.toUpperCase()}
              </span>
            </td>
            <td className="opponent-cell">{b.opponent}</td>
            <td className="turns-cell">{b.total_turns ?? '?'}</td>
            <td className="date-cell">
              {b.finished_at
                ? new Date(b.finished_at).toLocaleDateString()
                : '—'}
            </td>
            <td>
              <button
                className="btn-replay btn-replay-sm"
                onClick={() => onReplaySelected?.(b.id)}
                title="Watch replay"
              >
                ▶
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// ---------------------------------------------------------------------------
// Lessons log
// ---------------------------------------------------------------------------

function LessonsLog({ lessons }) {
  const [expanded, setExpanded] = useState(null)

  if (!lessons || lessons.length === 0) {
    return (
      <div className="lessons-empty">
        No lessons generated yet — lessons appear after battles with LLM players.
      </div>
    )
  }

  return (
    <ol className="lessons-list">
      {lessons.map((lesson, i) => (
        <li
          key={lesson.id}
          className={`lesson-item ${expanded === i ? 'expanded' : ''}`}
          onClick={() => setExpanded(expanded === i ? null : i)}
        >
          <div className="lesson-header">
            <span className="lesson-num">#{lessons.length - i}</span>
            <span className="lesson-date">
              {lesson.created_at
                ? new Date(lesson.created_at).toLocaleDateString()
                : ''}
            </span>
            <span className="lesson-expand">{expanded === i ? '▲' : '▼'}</span>
          </div>
          {expanded === i && (
            <div className="lesson-body">{lesson.content}</div>
          )}
          {expanded !== i && (
            <div className="lesson-preview">
              {lesson.content.slice(0, 100)}{lesson.content.length > 100 ? '…' : ''}
            </div>
          )}
        </li>
      ))}
    </ol>
  )
}

// ---------------------------------------------------------------------------
// Main ModelStats component
// ---------------------------------------------------------------------------

export default function ModelStats({ modelId, onClose, onReplaySelected }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (modelId == null) return
    setLoading(true)
    setError(null)
    fetch(`/api/models/${modelId}/stats`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`)
        return r.json()
      })
      .then(data => { setStats(data); setLoading(false) })
      .catch(err => { setError(err.message); setLoading(false) })
  }, [modelId])

  if (loading) {
    return (
      <div className="stats-page">
        <div className="stats-loading">Loading model stats…</div>
      </div>
    )
  }

  if (error || !stats) {
    return (
      <div className="stats-page">
        <button className="stats-back" onClick={onClose}>← BACK</button>
        <div className="stats-error">Failed to load stats: {error}</div>
      </div>
    )
  }

  const { model, elo_history, battle_history, turn_stats, lessons } = stats
  const winRate = model.games > 0
    ? ((model.wins / model.games) * 100).toFixed(1)
    : null

  return (
    <div className="stats-page">
      {/* Header */}
      <div className="stats-header">
        <button className="stats-back" onClick={onClose}>← BACK</button>
        <div className="stats-identity">
          <div className="stats-model-name">{model.model_name}</div>
          <div className="stats-provider-row">
            <span className="provider-tag">{model.provider}</span>
            <span className="version-tag">{model.prompt_version}</span>
          </div>
        </div>
        <div className="stats-kpis">
          <div className="kpi-block">
            <div className="kpi-value elo-value">{model.rating.toFixed(1)}</div>
            <div className="kpi-label">ELO</div>
          </div>
          <div className="kpi-block">
            <div className="kpi-value">
              <span className="w">{model.wins}W</span>
              {' / '}
              <span className="l">{model.losses}L</span>
              {' / '}
              {model.ties}T
            </div>
            <div className="kpi-label">RECORD ({model.games} games)</div>
          </div>
          {winRate != null && (
            <div className="kpi-block">
              <div className="kpi-value" style={{
                color: winRate >= 60 ? 'var(--accent-green)'
                     : winRate >= 40 ? 'var(--accent-amber)'
                     : 'var(--accent-red)'
              }}>
                {winRate}%
              </div>
              <div className="kpi-label">WIN RATE</div>
            </div>
          )}
        </div>
      </div>

      {/* ELO chart */}
      <div className="panel stats-panel">
        <EloSparkline history={elo_history} />
      </div>

      {/* Two-column: quality + battles */}
      <div className="stats-grid">
        <div className="panel stats-panel">
          <div className="panel-title">TURN QUALITY</div>
          <QualityBar turnStats={turn_stats} />
        </div>

        <div className="panel stats-panel">
          <div className="panel-title">BATTLE HISTORY</div>
          <BattleHistoryTable
            battles={battle_history}
            onReplaySelected={onReplaySelected}
          />
        </div>
      </div>

      {/* Lessons */}
      <div className="panel stats-panel">
        <div className="panel-title">
          BATTLE MEMORY
          <span className="panel-subtitle">
            {lessons.length} lesson{lessons.length !== 1 ? 's' : ''} accumulated
          </span>
        </div>
        <LessonsLog lessons={lessons} />
      </div>
    </div>
  )
}
