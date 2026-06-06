import { useState } from 'react'
import './styles/main.css'
import Leaderboard from './components/Leaderboard'
import BattleField from './components/BattleField'
import BattleReplay from './components/BattleReplay'
import ModelStats from './components/ModelStats'
import TournamentView from './components/TournamentView'
import { useBattleStream } from './hooks/useBattleStream'

function App() {
  const [view, setView]                       = useState('home')
  const [dismissed, setDismissed]             = useState(false)
  const [replayBattleId, setReplayBattleId]   = useState(null)
  const [statsModelId, setStatsModelId]       = useState(null)
  const [tournamentId, setTournamentId]       = useState(null)
  // Track where replay was launched from so Close returns there
  const [replayOrigin, setReplayOrigin]       = useState('home')
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

  function handleTournamentStarted(data) {
    reset()
    clearTournament()
    setDismissed(false)
    // Go directly to the tournament scoreboard; it has a "watch live" button
    if (data?.tournament_id) {
      setTournamentId(data.tournament_id)
      setView('tournament')
    } else {
      setView('battle')
    }
  }

  function handleTournamentSelected(id) {
    setTournamentId(id)
    setView('tournament')
  }

  function handleTournamentClose() {
    setTournamentId(null)
    setView('home')
  }

  function handleWatchLive() {
    setView('battle')
  }

  function handleReplaySelected(battleId) {
    setReplayOrigin(view)   // remember where we came from
    setReplayBattleId(battleId)
    setView('replay')
  }

  function handleReplayClose() {
    setReplayBattleId(null)
    // Return to origin: stats page, tournament view, or home
    if (replayOrigin === 'stats' && statsModelId != null) {
      setView('stats')
    } else if (replayOrigin === 'tournament' && tournamentId != null) {
      setView('tournament')
    } else {
      setView('home')
    }
  }

  function handleModelSelected(modelId) {
    setStatsModelId(modelId)
    setView('stats')
  }

  function handleStatsClose() {
    setStatsModelId(null)
    setView('home')
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
            className={`nav-btn ${view === 'home' || view === 'stats' || view === 'tournament' ? 'active' : ''}`}
            onClick={() => { setStatsModelId(null); setTournamentId(null); setView('home') }}
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
          {/* Quick-jump to active tournament scoreboard */}
          {tournament && tournamentId && (
            <button
              className={`nav-btn ${view === 'tournament' ? 'active' : ''}`}
              onClick={() => setView('tournament')}
            >
              SCORES
            </button>
          )}
        </nav>
      </header>

      <main>
        {view === 'home' && (
          <Leaderboard
            onBattleStarted={handleBattleStarted}
            onTournamentStarted={handleTournamentStarted}
            onReplaySelected={handleReplaySelected}
            onModelSelected={handleModelSelected}
            onTournamentSelected={handleTournamentSelected}
          />
        )}
        {view === 'stats' && statsModelId != null && (
          <ModelStats
            modelId={statsModelId}
            onClose={handleStatsClose}
            onReplaySelected={handleReplaySelected}
          />
        )}
        {view === 'tournament' && tournamentId != null && (
          <TournamentView
            tournamentId={tournamentId}
            tournament={tournament?.id === tournamentId ? tournament : null}
            onClose={handleTournamentClose}
            onWatchLive={handleWatchLive}
            onReplaySelected={handleReplaySelected}
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
            onTournamentScoreboard={() => {
              if (tournament?.id) {
                setTournamentId(tournament.id)
                setView('tournament')
              }
            }}
          />
        )}
        {view === 'replay' && replayBattleId != null && (
          <BattleReplay
            battleId={replayBattleId}
            onClose={handleReplayClose}
          />
        )}
      </main>
    </div>
  )
}

export default App
