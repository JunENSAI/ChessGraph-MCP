import { describe, expect, it } from 'vitest'
import { DEFAULT_MODE, MODES } from './modes'

describe('coach modes', () => {
  it('opens on Home', () => {
    expect(DEFAULT_MODE).toBe('recap')
    expect(MODES[0].id).toBe('recap')
    expect(MODES[0].label).toBe('Home')
  })

  it('labels every tab once', () => {
    const labels = MODES.map(mode => mode.label)
    expect(new Set(labels).size).toBe(labels.length)
    expect(labels).toContain('Training')
    expect(labels).toContain('My games')
  })
})
