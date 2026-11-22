export type Mode = 'recap' | 'training' | 'games'

export interface ModeSpec {
  id: Mode
  label: string
}

/** Recap is Home: first tab and the default view. */
export const MODES: ModeSpec[] = [
  { id: 'recap', label: 'Home' },
  { id: 'training', label: 'Play & train' },
  { id: 'games', label: 'My games' },
]

export const DEFAULT_MODE: Mode = 'recap'
