export type Color = 'white' | 'black'
export type Outcome = 'win' | 'loss' | 'draw'
export type GameCategory = 'rapid' | 'blitz' | 'bullet' | 'daily' | 'bot'

export interface TrainingStep {
  san: string
  explanation: string
}

export interface TrainingTrack {
  id: string
  kind: 'opening' | 'defense' | 'endgame'
  title: string
  subtitle: string
  userColor: Color
  startFen?: string
  /** Full lesson line in SAN; the user plays the moves of `userColor`. */
  line: TrainingStep[]
}

export interface KeyMoment {
  ply: number
  played: string
  best: string
  evalBefore: number
  evalAfter: number
  explanation: string
}

export interface LibraryGame {
  id: string
  category: GameCategory
  timeControl: string
  playedOn: string
  opponent: string
  opponentElo: number
  userElo: number
  userColor: Color
  result: Outcome
  opening: string
  eco: string
  moves: string[]
  keyMoment: KeyMoment
}

export interface OutcomeCounts {
  wins: number
  draws: number
  losses: number
}

export interface OpeningStat {
  name: string
  eco: string
  results: OutcomeCounts
}

export interface EndgameStat {
  type: string
  label: string
  white: OutcomeCounts
  black: OutcomeCounts
}

export interface RatingBand {
  id: string
  label: string
  white: OutcomeCounts
  black: OutcomeCounts
  openingsWhite: OpeningStat[]
  defensesBlack: OpeningStat[]
  endgames: EndgameStat[]
}

export interface TimeControlStat {
  id: GameCategory
  label: string
  results: OutcomeCounts
}

/** Recap band counted from stored games. Endgame types are not on those rows. */
export interface RecapBand {
  id: string
  label: string
  white: OutcomeCounts
  black: OutcomeCounts
  openingsWhite: OpeningStat[]
  defensesBlack: OpeningStat[]
  timeControls: TimeControlStat[]
}

export interface RecapPayload {
  gameCount: number
  bands: RecapBand[]
}
