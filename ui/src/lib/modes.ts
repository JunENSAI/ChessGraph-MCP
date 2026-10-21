export type Mode = 'recap' | 'training' | 'games'

export interface ModeSpec {
  id: Mode
  label: string
  /** Loaded lazily on first visit because the charts are a separate chunk. */
  lazy: boolean
}

/** Recap is Home: first tab and the default view. */
export const MODES: ModeSpec[] = [
  { id: 'recap', label: 'Home', lazy: true },
  { id: 'training', label: 'Training', lazy: false },
  { id: 'games', label: 'My games', lazy: false },
]

export const DEFAULT_MODE: Mode = 'recap'
