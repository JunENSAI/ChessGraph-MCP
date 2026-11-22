import { describe, expect, it } from 'vitest'
import { soundFor } from './sound'

describe('soundFor', () => {
  it('maps SAN to a sound', () => {
    expect(soundFor('e4')).toBe('move')
    expect(soundFor('Nxe5')).toBe('capture')
    expect(soundFor('O-O-O')).toBe('castle')
    expect(soundFor('Qxf7+')).toBe('check')
    expect(soundFor('Qxf7#')).toBe('end')
    expect(soundFor('e4', true)).toBe('end')
  })
})
