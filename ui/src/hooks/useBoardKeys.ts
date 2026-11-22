import { useEffect, useRef } from 'react'
import { boardAction, isTypingTarget } from '../lib/keys'

/**
 * ←/→ step, ↑/Home and ↓/End jump, F flips, on the active view only.
 * Handlers are read from a ref so the listener is attached once per activation.
 */
export function useBoardKeys(
  active: boolean,
  state: { index: number; last: number; go: (index: number) => void; flip: () => void },
) {
  const latest = useRef(state)
  useEffect(() => {
    latest.current = state
  })
  useEffect(() => {
    if (!active) return
    const onKey = (event: KeyboardEvent) => {
      if (event.altKey || event.ctrlKey || event.metaKey || isTypingTarget(event.target)) return
      const { index, last, go, flip } = latest.current
      const action = boardAction(event.key, index, last)
      if (!action) return
      event.preventDefault()
      if (action.type === 'flip') flip()
      else if (action.index !== index) go(action.index)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [active])
}
