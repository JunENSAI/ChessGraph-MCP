import { describe, expect, it } from 'vitest'
import { boardAction, isTypingTarget } from './keys'

describe('boardAction', () => {
  it('steps and clamps', () => {
    expect(boardAction('ArrowLeft', 0, 10)).toEqual({ type: 'go', index: 0 })
    expect(boardAction('ArrowRight', 3, 10)).toEqual({ type: 'go', index: 4 })
    expect(boardAction('ArrowRight', 10, 10)).toEqual({ type: 'go', index: 10 })
  })

  it('jumps to the ends and flips', () => {
    expect(boardAction('Home', 5, 10)).toEqual({ type: 'go', index: 0 })
    expect(boardAction('ArrowUp', 5, 10)).toEqual({ type: 'go', index: 0 })
    expect(boardAction('End', 5, 10)).toEqual({ type: 'go', index: 10 })
    expect(boardAction('ArrowDown', 5, 10)).toEqual({ type: 'go', index: 10 })
    expect(boardAction('f', 5, 10)).toEqual({ type: 'flip' })
    expect(boardAction('x', 5, 10)).toBeNull()
  })
})

describe('isTypingTarget', () => {
  it('leaves keys in form fields alone', () => {
    expect(isTypingTarget({ tagName: 'input' } as unknown as EventTarget)).toBe(true)
    expect(isTypingTarget({ tagName: 'SELECT' } as unknown as EventTarget)).toBe(true)
    expect(isTypingTarget({ tagName: 'DIV', isContentEditable: true } as unknown as EventTarget)).toBe(true)
    expect(isTypingTarget({ tagName: 'BUTTON' } as unknown as EventTarget)).toBe(false)
    expect(isTypingTarget(null)).toBe(false)
  })
})
