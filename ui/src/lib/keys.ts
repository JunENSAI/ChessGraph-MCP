/** What a key does on a board view. Pure, so every view navigates the same way. */
export type BoardAction = { type: 'go'; index: number } | { type: 'flip' } | null

/**
 * `index` is the current ply (0 = start position), `last` the number of plies.
 * ←/→ step, ↑/Home go to the start, ↓/End go to the end, F flips.
 */
export function boardAction(key: string, index: number, last: number): BoardAction {
  const clamp = (value: number) => Math.max(0, Math.min(last, value))
  switch (key) {
    case 'ArrowLeft':
      return { type: 'go', index: clamp(index - 1) }
    case 'ArrowRight':
      return { type: 'go', index: clamp(index + 1) }
    case 'ArrowUp':
    case 'Home':
      return { type: 'go', index: 0 }
    case 'ArrowDown':
    case 'End':
      return { type: 'go', index: last }
    case 'f':
    case 'F':
      return { type: 'flip' }
    default:
      return null
  }
}

/** Keys typed into a field belong to the field. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!target || typeof target !== 'object') return false
  const element = target as { tagName?: string; isContentEditable?: boolean }
  const tag = element.tagName?.toUpperCase()
  return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || element.isContentEditable === true
}
