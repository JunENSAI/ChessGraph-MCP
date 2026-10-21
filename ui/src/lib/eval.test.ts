import { describe, expect, it } from 'vitest'
import { formatWhiteEval, whiteEvalFromSide, whiteEvalFromStored, whiteShare } from './eval'

describe('whiteEvalFromStored', () => {
  it('keeps a white move as White centipawns', () => {
    expect(whiteEvalFromStored(140, 'w')).toEqual({ whiteCp: 140, mate: null })
  })

  it('flips a black move into White centipawns', () => {
    expect(whiteEvalFromStored(80, 'b')).toEqual({ whiteCp: -80, mate: null })
  })

  it('treats the stored mate sentinel as a full bar', () => {
    expect(whiteEvalFromStored(-10000, 'w').mate).toBe(-1)
  })
})

describe('whiteEvalFromSide', () => {
  it('flips a black-to-move centipawn score', () => {
    expect(whiteEvalFromSide(35, null, 'b')).toEqual({ whiteCp: -35, mate: null })
  })

  it('flips a mate scored for the side to move', () => {
    expect(whiteEvalFromSide(null, 3, 'b').mate).toBe(-3)
  })
})

describe('whiteShare', () => {
  it('fills the bar on mate and centers an empty score', () => {
    expect(whiteShare({ whiteCp: null, mate: 2 })).toBe(1)
    expect(whiteShare({ whiteCp: null, mate: -4 })).toBe(0)
    expect(whiteShare({ whiteCp: null, mate: null })).toBe(0.5)
  })

  it('clamps a large centipawn score at five pawns', () => {
    expect(whiteShare({ whiteCp: 500, mate: null })).toBe(1)
    expect(whiteShare({ whiteCp: 250, mate: null })).toBe(0.75)
  })
})

describe('formatWhiteEval', () => {
  it('prints pawns from White and a mate marker', () => {
    expect(formatWhiteEval({ whiteCp: -120, mate: null })).toBe('-1.2')
    expect(formatWhiteEval({ whiteCp: null, mate: -3 })).toBe('-M3')
  })
})
