import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * useTooltip — tracks hover state with a short delay to avoid flicker.
 *
 * Returns { anchor, onEnter, onLeave }
 *   anchor: DOMRect | null (null = hidden)
 *   onEnter: attach to onMouseEnter
 *   onLeave: attach to onMouseLeave
 */
export function useTooltip(delayMs = 250) {
  const [anchor, setAnchor] = useState(null)
  const timerRef = useRef(null)

  const onEnter = useCallback((e) => {
    const rect = e.currentTarget.getBoundingClientRect()
    timerRef.current = setTimeout(() => setAnchor(rect), delayMs)
  }, [delayMs])

  const onLeave = useCallback(() => {
    clearTimeout(timerRef.current)
    setAnchor(null)
  }, [])

  // Clean up on unmount
  useEffect(() => () => clearTimeout(timerRef.current), [])

  return { anchor, onEnter, onLeave }
}
