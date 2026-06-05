import { useState, useEffect } from 'react'
import BattleAnalysis from './BattleAnalysis'

const PROVIDERS = ['random', 'anthropic', 'openai', 'lmstudio']

export default function Leaderboard({ onBattleStarted }) {
  const [rows, setRows]         = useState([])
  const [battles, setBattles]   = useState([])
  const [loading, setLoading]   = useState(false)
  const [analyzing, setAnalyzing] = useState(null) // battle id being analyzed
  const [form, setForm]         = useState({
    p1_provider: 'random', p2_provider: 'anthropic',
    model: '', n_battles: 1,
  })

  async function fetchData() {
    try {
      const [lb, bt] = await Promise.all([
        fetch('/api/leaderboard').then(r => r.json()),
        fetch('/api/battles').then(r => r.json()),
      ])
      setRows(lb)
      setBattles(bt)
    } catch {}
  }

  useEffect(() => { fetchData() }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const body = { ...form, n_battles: Number(form.n_battles) }
      if (!body.model) delete body.model
      const res = await fetch('/api/battles/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      const data = await res.json()
      if (res.ok) {
        onBattleStarted?.(data)
      }
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  function rankBadge(i) {
    if (i === 0) return <span className="rank-badge gold">①</span>
    if (i === 1) return <span className="rank-badge silver">②</span>
    if (i === 2) return <span className="rank-badge bronze">③</span>
    return <span className="rank-badge">{i + 1}</span>
  }

  return (
    <div className="home-grid">
      {/* Left: leaderboard + recent battles */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
        <div className="panel">
          <div className="panel-title">ELO LEADERBOARD</div>
          {rows.length === 0 ? (
            <div className="empty-state">No battles recorded yet</div>
          ) : (
            <table className="leaderboard-table">
              <thead>
                <tr>
                  <th>#</th>
                  <th>MODEL</th>
                  <th>ELO</th>
                  <th>GAMES</th>
                  <th>W / L / T</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i}>
                    <td>{rankBadge(i)}</td>
                    <td>
                      <div className="model-name">{r.model_name}</div>
                      <div className="provider-tag">{r.provider} · {r.prompt_version}</div>
                    </td>
                    <td><span className="elo-value">{r.rating.toFixed(1)}</span></td>
                    <td>{r.games}</td>
                    <td className="wlt">
                      <span className="w">{r.wins}W</span>
                      {' / '}
                      <span className="l">{r.losses}L</span>
                      {' / '}
                      {r.ties}T
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>

        <div className="panel">
          <div className="panel-title">RECENT BATTLES</div>
          {battles.length === 0 ? (
            <div className="empty-state">No battles yet</div>
          ) : (
            battles.map((b, i) => {
              const winnerCls = b.winner === 1 ? 'winner-p1' : b.winner === 2 ? 'winner-p2' : 'winner-tie'
              const winnerLabel = b.winner === 1 ? 'p1 wins' : b.winner === 2 ? 'p2 wins' : 'tie'
              const isOpen = analyzing === b.id
              return (
                <div key={i} className="battle-entry-wrap">
                  <div className="battle-entry">
                    <div className="battle-matchup">
                      <span>{b.p1}</span>
                      <span className="battle-vs">vs</span>
                      <span>{b.p2}</span>
                    </div>
                    <div className="battle-meta">
                      <div className={winnerCls}>{winnerLabel}</div>
                      <div>{b.total_turns ?? '?'} turns</div>
                      <button
                        className={`btn-analyze ${isOpen ? 'active' : ''}`}
                        onClick={() => setAnalyzing(isOpen ? null : b.id)}
                      >
                        {isOpen ? '▲ HIDE' : '▼ ANALYZE'}
                      </button>
                    </div>
                  </div>
                  {isOpen && <BattleAnalysis battleId={b.id} />}
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Right: start battle form */}
      <div className="panel">
        <div className="panel-title">START BATTLE</div>
        <form className="start-form" onSubmit={handleSubmit}>
          <div className="form-row">
            <div className="form-group">
              <label className="form-label">P1 Provider</label>
              <select
                className="form-select"
                value={form.p1_provider}
                onChange={e => setForm(f => ({ ...f, p1_provider: e.target.value }))}
              >
                {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">P2 Provider</label>
              <select
                className="form-select"
                value={form.p2_provider}
                onChange={e => setForm(f => ({ ...f, p2_provider: e.target.value }))}
              >
                {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
              </select>
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Model override (optional)</label>
            <input
              className="form-input"
              placeholder="e.g. claude-opus-4-8"
              value={form.model}
              onChange={e => setForm(f => ({ ...f, model: e.target.value }))}
            />
          </div>

          <div className="form-group">
            <label className="form-label">Number of battles</label>
            <input
              className="form-input"
              type="number" min="1" max="20"
              value={form.n_battles}
              onChange={e => setForm(f => ({ ...f, n_battles: e.target.value }))}
            />
          </div>

          <button className="btn-start" type="submit" disabled={loading}>
            {loading ? '▶ STARTING…' : '▶ START BATTLE'}
          </button>
        </form>
      </div>
    </div>
  )
}
