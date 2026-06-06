import { useState, useEffect } from 'react'
import BattleAnalysis from './BattleAnalysis'

const PROVIDERS = ['random', 'anthropic', 'openai', 'lmstudio']

// Static fallback presets for cloud providers
const STATIC_PRESETS = {
  anthropic: [
    { label: 'Sonnet 4.5', value: 'claude-sonnet-4-5' },
    { label: 'Haiku 3.5', value: 'claude-haiku-3-5' },
  ],
  openai: [
    { label: 'GPT-4o mini', value: 'gpt-4o-mini' },
    { label: 'GPT-4o', value: 'gpt-4o' },
  ],
}

/**
 * Fetches available LM Studio models from the backend proxy.
 * Returns [] if LM Studio is offline — UI falls back to free-text input.
 */
async function fetchLMStudioModels() {
  try {
    const res = await fetch('/api/lmstudio/models')
    if (!res.ok) return []
    return await res.json()   // string[]
  } catch {
    return []
  }
}

function ModelSelector({ label, provider, model, onProviderChange, onModelChange, lmModels, lmLoading }) {
  // For lmstudio: show live chips; for cloud providers: show static chips
  const chips = provider === 'lmstudio'
    ? lmModels.map(id => ({ label: id.split('/').pop(), value: id }))
    : (STATIC_PRESETS[provider] || [])

  return (
    <div className="model-selector">
      <label className="form-label">{label}</label>
      <div className="model-selector-row">
        <select
          className="form-select provider-select"
          value={provider}
          onChange={e => {
            onProviderChange(e.target.value)
            onModelChange('')  // clear model on provider change
          }}
        >
          {PROVIDERS.map(p => <option key={p} value={p}>{p}</option>)}
        </select>
        <input
          className="form-input model-input"
          placeholder={provider === 'random' ? '—' : 'model id'}
          value={model}
          disabled={provider === 'random'}
          onChange={e => onModelChange(e.target.value)}
        />
      </div>

      {provider === 'lmstudio' && lmLoading && (
        <div className="model-presets-status">querying LM Studio…</div>
      )}
      {provider === 'lmstudio' && !lmLoading && lmModels.length === 0 && (
        <div className="model-presets-status offline">LM Studio offline — enter model id manually</div>
      )}

      {chips.length > 0 && provider !== 'random' && (
        <div className="model-presets">
          {chips.map(p => (
            <button
              key={p.value}
              type="button"
              className={`preset-chip ${model === p.value ? 'active' : ''}`}
              onClick={() => onModelChange(p.value)}
              title={p.value}
            >
              {p.label}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

export default function Leaderboard({ onBattleStarted }) {
  const [rows, setRows]           = useState([])
  const [battles, setBattles]     = useState([])
  const [loading, setLoading]     = useState(false)
  const [analyzing, setAnalyzing] = useState(null)
  const [lmModels, setLmModels]   = useState([])
  const [lmLoading, setLmLoading] = useState(true)
  const [form, setForm]           = useState({
    p1_provider: 'lmstudio', p2_provider: 'lmstudio',
    p1_model: '', p2_model: '',
    n_battles: 1,
  })

  // Fetch LM Studio models once on mount; auto-select first two if form is blank
  useEffect(() => {
    let cancelled = false
    setLmLoading(true)
    fetchLMStudioModels().then(models => {
      if (cancelled) return
      setLmModels(models)
      setLmLoading(false)
      // Auto-fill model inputs with first two loaded models
      if (models.length > 0) {
        setForm(f => ({
          ...f,
          p1_model: f.p1_model || models[0] || '',
          p2_model: f.p2_model || models[1] || models[0] || '',
        }))
      }
    })
    return () => { cancelled = true }
  }, [])

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

  useEffect(() => {
    fetchData()
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [])

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const body = { ...form, n_battles: Number(form.n_battles) }
      if (!body.p1_model || body.p1_provider === 'random') delete body.p1_model
      if (!body.p2_model || body.p2_provider === 'random') delete body.p2_model
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
                      <div className="provider-tag">
                        {r.provider}
                        {r.versions && (
                          <span className="version-tags">
                            {r.versions.split(',').map(v => (
                              <span key={v} className="version-tag">{v}</span>
                            ))}
                          </span>
                        )}
                      </div>
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
              const winnerCls   = b.winner === 1 ? 'winner-p1' : b.winner === 2 ? 'winner-p2' : 'winner-tie'
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

          <ModelSelector
            label="PLAYER 1"
            provider={form.p1_provider}
            model={form.p1_model}
            onProviderChange={v => setForm(f => ({ ...f, p1_provider: v }))}
            onModelChange={v => setForm(f => ({ ...f, p1_model: v }))}
            lmModels={lmModels}
            lmLoading={lmLoading}
          />

          <ModelSelector
            label="PLAYER 2"
            provider={form.p2_provider}
            model={form.p2_model}
            onProviderChange={v => setForm(f => ({ ...f, p2_provider: v }))}
            onModelChange={v => setForm(f => ({ ...f, p2_model: v }))}
            lmModels={lmModels}
            lmLoading={lmLoading}
          />

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
