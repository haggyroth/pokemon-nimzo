import { useState, useEffect } from 'react'
import BattleAnalysis from './BattleAnalysis'

const PROVIDERS = ['random', 'anthropic', 'openai', 'lmstudio']

const STATIC_PRESETS = {
  anthropic: [
    { label: 'Sonnet 4.5', value: 'claude-sonnet-4-5' },
    { label: 'Haiku 3.5',  value: 'claude-haiku-3-5'  },
  ],
  openai: [
    { label: 'GPT-4o mini', value: 'gpt-4o-mini' },
    { label: 'GPT-4o',      value: 'gpt-4o'      },
  ],
}

async function fetchLMStudioModels() {
  try {
    const res = await fetch('/api/lmstudio/models')
    if (!res.ok) return []
    return await res.json()
  } catch {
    return []
  }
}

// ---------------------------------------------------------------------------
// Shared model selector component
// ---------------------------------------------------------------------------

function ModelSelector({ label, provider, model, onProviderChange, onModelChange, lmModels, lmLoading }) {
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
          onChange={e => { onProviderChange(e.target.value); onModelChange('') }}
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

// ---------------------------------------------------------------------------
// Single-battle form
// ---------------------------------------------------------------------------

function BattleForm({ onBattleStarted, lmModels, lmLoading }) {
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    p1_provider: 'lmstudio', p2_provider: 'lmstudio',
    p1_model: '', p2_model: '',
    n_battles: 1,
  })

  // Auto-fill with first two LM Studio models once they load.
  // Deferred to a microtask so setState is not called synchronously inside
  // the effect body (react-hooks/set-state-in-effect).
  useEffect(() => {
    if (lmModels.length === 0) return
    void Promise.resolve().then(() =>
      setForm(f => ({
        ...f,
        p1_model: f.p1_model || lmModels[0] || '',
        p2_model: f.p2_model || lmModels[1] || lmModels[0] || '',
      }))
    )
  }, [lmModels])

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
      if (res.ok) onBattleStarted?.(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form className="start-form" onSubmit={handleSubmit}>
      <ModelSelector
        label="PLAYER 1"
        provider={form.p1_provider} model={form.p1_model}
        onProviderChange={v => setForm(f => ({ ...f, p1_provider: v }))}
        onModelChange={v => setForm(f => ({ ...f, p1_model: v }))}
        lmModels={lmModels} lmLoading={lmLoading}
      />
      <ModelSelector
        label="PLAYER 2"
        provider={form.p2_provider} model={form.p2_model}
        onProviderChange={v => setForm(f => ({ ...f, p2_provider: v }))}
        onModelChange={v => setForm(f => ({ ...f, p2_model: v }))}
        lmModels={lmModels} lmLoading={lmLoading}
      />
      <div className="form-group">
        <label className="form-label">Number of battles</label>
        <input
          className="form-input" type="number" min="1" max="20"
          value={form.n_battles}
          onChange={e => setForm(f => ({ ...f, n_battles: e.target.value }))}
        />
      </div>
      <button className="btn-start" type="submit" disabled={loading}>
        {loading ? '▶ STARTING…' : '▶ START BATTLE'}
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Tournament form
// ---------------------------------------------------------------------------

const EMPTY_PLAYER = { provider: 'lmstudio', model: '' }

function TournamentForm({ onTournamentStarted, lmModels }) {
  const [loading, setLoading] = useState(false)
  const [rounds, setRounds] = useState(3)
  const [players, setPlayers] = useState([
    { ...EMPTY_PLAYER },
    { ...EMPTY_PLAYER },
  ])

  // Auto-fill first two with LM Studio models once they load.
  useEffect(() => {
    if (lmModels.length === 0) return
    void Promise.resolve().then(() =>
      setPlayers(prev => prev.map((p, i) => ({
        ...p,
        model: p.model || lmModels[i] || lmModels[0] || '',
      })))
    )
  }, [lmModels])

  function setPlayer(i, field, value) {
    setPlayers(prev => prev.map((p, idx) =>
      idx === i ? { ...p, [field]: value, ...(field === 'provider' ? { model: '' } : {}) } : p
    ))
  }

  function addPlayer() {
    if (players.length >= 6) return
    setPlayers(prev => [...prev, { ...EMPTY_PLAYER, model: lmModels[prev.length] || '' }])
  }

  function removePlayer(i) {
    if (players.length <= 2) return
    setPlayers(prev => prev.filter((_, idx) => idx !== i))
  }

  const totalBattles = (() => {
    const n = players.length
    return n >= 2 ? (n * (n - 1)) * rounds : 0
  })()

  async function handleSubmit(e) {
    e.preventDefault()
    setLoading(true)
    try {
      const payload = {
        players: players.map(p => ({
          provider: p.provider,
          model: p.provider === 'random' ? null : (p.model || null),
        })),
        rounds: Number(rounds),
      }
      const res = await fetch('/api/tournament/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (res.ok) onTournamentStarted?.(data)
    } catch (err) {
      console.error(err)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form className="start-form" onSubmit={handleSubmit}>
      <div className="tournament-players-header">
        <label className="form-label">PLAYERS</label>
        {players.length < 6 && (
          <button type="button" className="btn-add-player" onClick={addPlayer}>+ ADD</button>
        )}
      </div>

      {players.map((p, i) => (
        <div key={i} className="tournament-player-row">
          <div className="tournament-player-label">
            P{i + 1}
            {players.length > 2 && (
              <button type="button" className="btn-remove-player" onClick={() => removePlayer(i)}>✕</button>
            )}
          </div>
          <div className="tournament-player-inputs">
            <select
              className="form-select provider-select"
              value={p.provider}
              onChange={e => setPlayer(i, 'provider', e.target.value)}
            >
              {PROVIDERS.map(pv => <option key={pv} value={pv}>{pv}</option>)}
            </select>
            <input
              className="form-input model-input"
              placeholder={p.provider === 'random' ? '—' : 'model id'}
              value={p.model}
              disabled={p.provider === 'random'}
              onChange={e => setPlayer(i, 'model', e.target.value)}
            />
          </div>
          {p.provider === 'lmstudio' && lmModels.length > 0 && (
            <div className="model-presets" style={{ paddingLeft: '1.8rem' }}>
              {lmModels.slice(0, 4).map(id => (
                <button
                  key={id} type="button"
                  className={`preset-chip ${p.model === id ? 'active' : ''}`}
                  onClick={() => setPlayer(i, 'model', id)}
                  title={id}
                >
                  {id.split('/').pop()}
                </button>
              ))}
            </div>
          )}
        </div>
      ))}

      <div className="form-group">
        <label className="form-label">Rounds per matchup</label>
        <input
          className="form-input" type="number" min="1" max="10"
          value={rounds}
          onChange={e => setRounds(e.target.value)}
        />
        {totalBattles > 0 && (
          <div className="tournament-battle-count">{totalBattles} battles total</div>
        )}
      </div>

      <button className="btn-start" type="submit" disabled={loading || players.length < 2}>
        {loading ? '⚔ STARTING…' : `⚔ START TOURNAMENT`}
      </button>
    </form>
  )
}

// ---------------------------------------------------------------------------
// Main Leaderboard component
// ---------------------------------------------------------------------------

export default function Leaderboard({ onBattleStarted, onTournamentStarted, onReplaySelected, onModelSelected }) {
  const [rows, setRows]           = useState([])
  const [battles, setBattles]     = useState([])
  const [analyzing, setAnalyzing] = useState(null)
  const [lmModels, setLmModels]   = useState([])
  const [lmLoading, setLmLoading] = useState(true)
  const [formTab, setFormTab]     = useState('battle')   // 'battle' | 'tournament'

  useEffect(() => {
    let cancelled = false
    async function loadModels() {
      setLmLoading(true)
      const models = await fetchLMStudioModels()
      if (cancelled) return
      setLmModels(models)
      setLmLoading(false)
    }
    loadModels()
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
    } catch {
      // network errors are silently swallowed; UI retains stale data
    }
  }

  useEffect(() => {
    void Promise.resolve().then(fetchData)
    const id = setInterval(fetchData, 30000)
    return () => clearInterval(id)
  }, [])

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
                  <th>#</th><th>MODEL</th><th>ELO</th><th>GAMES</th><th>W / L / T</th><th></th>
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
                    <td>
                      {r.model_id != null && (
                        <button
                          className="btn-stats"
                          onClick={() => onModelSelected?.(r.model_id)}
                          title="View model stats"
                        >
                          STATS →
                        </button>
                      )}
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
                      {b.status === 'completed' && (
                        <button
                          className="btn-replay"
                          onClick={() => onReplaySelected?.(b.id)}
                          title="Watch replay"
                        >
                          ▶ REPLAY
                        </button>
                      )}
                    </div>
                  </div>
                  {isOpen && (
                    <BattleAnalysis
                      battleId={b.id}
                      p1Label={b.p1?.split('/').pop() ?? 'P1'}
                      p2Label={b.p2?.split('/').pop() ?? 'P2'}
                    />
                  )}
                </div>
              )
            })
          )}
        </div>
      </div>

      {/* Right: tabbed battle / tournament form */}
      <div className="panel">
        <div className="form-tabs">
          <button
            className={`form-tab ${formTab === 'battle' ? 'active' : ''}`}
            onClick={() => setFormTab('battle')}
          >
            ▶ BATTLE
          </button>
          <button
            className={`form-tab ${formTab === 'tournament' ? 'active' : ''}`}
            onClick={() => setFormTab('tournament')}
          >
            ⚔ TOURNAMENT
          </button>
        </div>

        {formTab === 'battle' ? (
          <BattleForm
            onBattleStarted={onBattleStarted}
            lmModels={lmModels}
            lmLoading={lmLoading}
          />
        ) : (
          <TournamentForm
            onTournamentStarted={onTournamentStarted}
            lmModels={lmModels}
            lmLoading={lmLoading}
          />
        )}
      </div>
    </div>
  )
}
