/**
 * EmptyState — shared no-data / onboarding placeholder.
 *
 * Centered icon + title + optional hint + optional action. Used wherever a list
 * or panel has nothing to show yet, so the first-run experience reads as
 * intentional rather than broken. Styled with the design tokens (--space-*,
 * --fs-*) so it stays consistent across surfaces.
 */
export default function EmptyState({ icon = '◊', title, hint, action, compact = false }) {
  return (
    <div className={`empty-state-box${compact ? ' empty-state-box--compact' : ''}`}>
      <div className="empty-state-icon" aria-hidden="true">{icon}</div>
      <div className="empty-state-title">{title}</div>
      {hint && <div className="empty-state-hint">{hint}</div>}
      {action && <div className="empty-state-action">{action}</div>}
    </div>
  )
}
