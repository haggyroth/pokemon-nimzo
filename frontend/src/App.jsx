import { useState } from 'react'
import './styles/main.css'
import Leaderboard from './components/Leaderboard'
import BattleField from './components/BattleField'
import { useBattleStream } from './hooks/useBattleStream'

function App() {
  const [view, setView] = useState('home')
  const [dismissed, setDismissed] = useState(false)
  const {
    events, isConnected, p1State, p2State, battleInfo, battleResult,
    thinking, tournament, reset, clearTournament,
  } = useBattleStream()

  const result = dismissed ? null : battleResult

  function handleBattleStarted() {
    reset()
    setDismissed(false)
    setView('battle')
  }

  function handleTournamentStarted() {
    reset()
    clearTournament()
    setDismissed(false)
    setView('battle')
  }

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="app-logo">
          NIDOZO
          <span>LLM POKÉMON BATTLE ARENA</span>
        </div>
        <nav className="app-nav">
          <button
            className={`nav-btn ${view === 'home' ? 'active' : ''}`}
            onClick={() => setView('home')}
          >HOME</button>
          <button
            className={`nav-btn ${view === 'battle' ? 'active' : ''}`}
            onClick={() => setView('battle')}
          >
            <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
            LIVE
            {tournament && tournament.status === 'running' && (
              <span className="nav-tournament-badge">
                {tournament.done}/{tournament.total}
              </span>
            )}
          </button>
        </nav>
      </header>

      <main>
        {view === 'home' && (
          <Leaderboard
            onBattleStarted={handleBattleStarted}
            onTournamentStarted={handleTournamentStarted}
          />
        )}
        {view === 'battle' && (
          <BattleField
            p1State={p1State}
            p2State={p2State}
            battleInfo={battleInfo}
            battleResult={result}
            events={events}
            thinking={thinking}
            tournament={tournament}
            onDismiss={() => setDismissed(true)}
          />
        )}
      </main>
    </div>
  )
}

export default App
