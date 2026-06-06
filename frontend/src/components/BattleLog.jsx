import { useEffect, useRef } from 'react'

function formatEntry(event) {
  if (event.type === 'battle_start') {
    return { cls: 'start-event', text: `▶ Battle started — ${event.p1} vs ${event.p2}` }
  }
  if (event.type === 'battle_end') {
    const w = event.winner === 1 ? 'P1' : event.winner === 2 ? 'P2' : 'Tie'
    return { cls: 'end-event', text: `■ Battle over — ${w} wins after ${event.total_turns} turns` }
  }
  if (event.type === 'error') {
    return { cls: 'error-event', text: `✕ Error: ${event.message}` }
  }
  if (event.type === 'turn') {
    const role = event.player_role
    const roleCls = `log-role-${role}`
    const opp = role === 'p1' ? event.state?.opponent_active : event.state?.my_active
    const oppHp = opp ? ` · opp ${Math.round((opp.hp_fraction ?? 1) * 100)}% HP` : ''
    const action = event.action?.split('/').pop() || '?'
    return {
      cls: 'turn-event',
      jsx: (
        <span>
          <span className="log-turn-num">T{event.turn}</span>
          <span className={roleCls}>{role.toUpperCase()}</span>
          <span className="log-action"> → {action.replace('|/choose ', '')}</span>
          <span className="log-hp">{oppHp}</span>
        </span>
      ),
    }
  }
  return null
}

export default function BattleLog({ events }) {
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [events.length])

  const entries = events
    .map((e, i) => ({ ...formatEntry(e, i), key: i }))
    .filter(Boolean)

  return (
    <div className="battle-log-panel">
      <div className="battle-log-header">
        <span className="battle-log-title">BATTLE LOG</span>
        <span className="log-count">{entries.length} events</span>
      </div>
      <div className="battle-log-entries">
        {entries.length === 0 && (
          <div className="empty-state">Waiting for battle events…</div>
        )}
        {entries.map(({ cls, text, jsx, key }) => (
          <div key={key} className={`log-entry ${cls}`}>
            {jsx ?? text}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
