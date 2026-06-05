export default function HPBar({ fraction = 1 }) {
  const pct  = Math.max(0, Math.min(1, fraction))
  const tier = pct > 0.5 ? 'high' : pct > 0.25 ? 'mid' : 'low'

  return (
    <div className="hp-container">
      <div className="hp-label">
        <span className="hp-text">HP</span>
        <span className={`hp-pct ${tier}`}>{Math.round(pct * 100)}%</span>
      </div>
      <div className="hp-track">
        <div
          className={`hp-fill ${tier}`}
          style={{ width: `${pct * 100}%` }}
        />
      </div>
    </div>
  )
}
