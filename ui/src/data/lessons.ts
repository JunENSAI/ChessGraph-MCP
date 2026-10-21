import { Chess } from 'chess.js'
import { endgameTitle } from './openings'
import { tryUci } from '../lib/chess'
import type { Color, TrainingStep } from './types'

export const LESSON_PLIES = 12

export interface OpeningLesson {
  openingName: string
  ecoCode: string | null
  games: number
  uciLine: string | null
  pgnLine: string | null
}

export interface EndgameLesson {
  endgameType: string
  fenFull: string
  humanMoveUci: string
  eloTier: string | null
  pieceCount: number
}

export interface LessonSession {
  id: string
  title: string
  detail: string
  userColor: Color
  startFen: string
  line: TrainingStep[]
  /** After the scripted line, Stockfish plays the other side. */
  engineAfter: boolean
  /** Every opponent move comes from Stockfish. */
  enginePlay: boolean
  missingLine: boolean
  /** When true, the board plays the whole line before the user repeats it. */
  watch: boolean
}

interface OpeningLessonJson {
  opening_name: string
  eco_code: string | null
  games: number
  uci_line: string | null
  pgn_line: string | null
}

interface EndgameLessonJson {
  endgame_type: string
  fen_full: string
  human_move_uci: string
  elo_tier: string | null
  piece_count: number
}

const BOOK = 'Book move from the stored theory line.'

function stepsFromMoves(sans: string[]): TrainingStep[] {
  return sans.map(san => ({ san, explanation: BOOK }))
}

export function lineFromUci(uciLine: string, maxPlies = LESSON_PLIES, startFen?: string): TrainingStep[] {
  const chess = startFen ? new Chess(startFen) : new Chess()
  const steps: TrainingStep[] = []
  for (const token of uciLine.split(/[\s,]+/).filter(Boolean)) {
    const applied = tryUci(chess.fen(), token)
    if (!applied) break
    chess.load(applied.fen)
    steps.push({ san: applied.san, explanation: BOOK })
    if (steps.length >= maxPlies) break
  }
  return steps
}

/** How many plies the drill will actually play, for display. */
export function drillLength(session: LessonSession): number {
  return session.line.length
}

export function drillNote(session: LessonSession): string {
  if (session.missingLine) return 'No stored line for this drill.'
  return `${session.line.length} plies. You play ${session.userColor === 'white' ? 'White' : 'Black'}.`
}

export function lineFromPgn(pgnLine: string, maxPlies = LESSON_PLIES): TrainingStep[] {
  const chess = new Chess()
  const sans: string[] = []
  const tokens = pgnLine
    .replace(/\{[^}]*\}/g, ' ')
    .replace(/\([^)]*\)/g, ' ')
    .split(/\s+/)
  for (const token of tokens) {
    if (!token || /^\d+\.+$/.test(token) || /^(1-0|0-1|1\/2-1\/2|\*)$/.test(token)) continue
    try {
      const move = chess.move(token)
      sans.push(move.san)
    } catch {
      break
    }
    if (sans.length >= maxPlies) break
  }
  return stepsFromMoves(sans)
}

export function sessionFromOpening(lesson: OpeningLesson, userColor: Color): LessonSession {
  const line = lesson.uciLine
    ? lineFromUci(lesson.uciLine)
    : lesson.pgnLine
      ? lineFromPgn(lesson.pgnLine)
      : []
  const missingLine = line.length === 0
  return {
    id: `${userColor}:${lesson.openingName}`,
    title: lesson.openingName,
    detail: missingLine
      ? 'No stored theory line for this opening.'
      : `${lesson.games} games as ${userColor === 'white' ? 'White' : 'Black'}`,
    userColor,
    startFen: new Chess().fen(),
    line,
    engineAfter: false,
    enginePlay: false,
    missingLine,
    watch: false,
  }
}

export function sessionFromEndgame(lesson: EndgameLesson): LessonSession | null {
  let start: Chess
  try {
    start = new Chess(lesson.fenFull)
  } catch {
    return null
  }
  const userColor: Color = start.turn() === 'w' ? 'white' : 'black'
  const applied = tryUci(lesson.fenFull, lesson.humanMoveUci)
  const line: TrainingStep[] = applied
    ? [{ san: applied.san, explanation: 'This is the stored technique move.' }]
    : []
  return {
    id: `endgame:${lesson.endgameType}:${lesson.fenFull}`,
    title: endgameTitle(lesson.endgameType),
    detail: applied
      ? `${lesson.pieceCount} pieces · ${lesson.eloTier ?? 'stored position'}`
      : 'The stored technique move is not legal in this position.',
    userColor,
    startFen: lesson.fenFull,
    line,
    engineAfter: true,
    enginePlay: line.length === 0,
    missingLine: false,
    watch: false,
  }
}

export interface CoachingSplit {
  fen: string
  ply: number
  played_san: string
  played_uci: string
  best_uci: string
  best_san: string
  times: number
  average_cp_loss: number
  mate: boolean
}

export interface CoachingLine {
  family: string
  games: number
  wins: number
  draws: number
  losses: number
}

export interface TrainingTask {
  kind: 'opening' | 'defense' | 'endgame' | 'puzzle'
  title: string
  reason: string
  start_fen: string
  uci_line: string
  pgn_line: string
  user_color: Color
  ready: boolean
  puzzle_fens: string[]
}

export interface CoachingBrief {
  strengths: CoachingLine[]
  target: (CoachingLine & { splits: CoachingSplit[] }) | null
  calculation: CoachingSplit[]
  endgames: string
  tasks: TrainingTask[]
}

export function playableFen(fen: string): string {
  const fields = fen.trim().split(/\s+/)
  if (fields.length >= 6) return fields.slice(0, 6).join(' ')
  return `${fields.slice(0, 4).join(' ')} 0 1`
}

export function courseNote(brief: CoachingBrief): string {
  const strength = brief.strengths[0]
  const target = brief.target
  const split = target?.splits[0]
  const parts: string[] = []
  if (strength) parts.push(`${strength.family} is a strength (${strength.wins} wins in ${strength.games} games).`)
  if (target && split) {
    const stored = split.mate ? 'a mate' : split.best_san
    parts.push(`In the ${target.family} you played ${split.played_san} ${split.times} times. Stockfish stored ${stored}.`)
  } else if (target) {
    parts.push(`${target.family} is the line to work on. No repeated leaving move is stored.`)
  } else parts.push('No opening has enough games for a target yet.')
  return parts.join(' ')
}

export function splitSession(family: string, split: CoachingSplit): LessonSession {
  const startFen = playableFen(split.fen)
  const userColor: Color = sideFromFen(startFen)
  const stored = split.mate ? 'a mate' : split.best_san
  return {
    id: `split:${split.fen}`,
    title: family,
    detail: `You played ${split.played_san}. Stockfish stored ${stored}. Play that move from here.`,
    userColor,
    startFen,
    line: [],
    engineAfter: false,
    enginePlay: true,
    missingLine: false,
    watch: false,
  }
}

function sideFromFen(fen: string): Color {
  return fen.split(/\s+/)[1] === 'b' ? 'black' : 'white'
}

export function sessionFromTask(task: TrainingTask, uciLine = task.uci_line): LessonSession {
  const startFen = playableFen(task.start_fen)
  const line = uciLine
    ? lineFromUci(uciLine, Math.max(uciLine.split(/\s+/).length, 1), startFen)
    : task.pgn_line
      ? lineFromPgn(task.pgn_line)
      : []
  return {
    id: `task:${task.kind}`,
    title: task.title,
    detail: task.reason,
    userColor: task.user_color,
    startFen,
    line,
    engineAfter: false,
    enginePlay: false,
    missingLine: line.length === 0,
    watch: task.kind !== 'puzzle',
  }
}

export function playSession(userColor: Color): LessonSession {
  const side = userColor === 'white' ? 'White' : 'Black'
  return {
    id: `play:${userColor}`,
    title: `Play as ${side}`,
    detail: 'Stockfish plays the other side. Reading the explanation does not stop your clock.',
    userColor,
    startFen: new Chess().fen(),
    line: [],
    engineAfter: false,
    enginePlay: true,
    missingLine: false,
    watch: false,
  }
}

async function readError(response: Response, fallback: string): Promise<string> {
  try {
    const body = (await response.json()) as { error?: string }
    if (body.error) return body.error
  } catch {
    // Keep the fallback when the body is not JSON.
  }
  return fallback
}

export async function loadOpeningLessons(color: Color): Promise<OpeningLesson[]> {
  const response = await fetch(`/api/lessons/openings?color=${color}&limit=40`)
  if (!response.ok) throw new Error(await readError(response, `Opening list failed (${response.status}).`))
  const body = (await response.json()) as { lessons?: OpeningLessonJson[] }
  return (body.lessons ?? []).map(lesson => ({
    openingName: lesson.opening_name,
    ecoCode: lesson.eco_code,
    games: lesson.games,
    uciLine: lesson.uci_line,
    pgnLine: lesson.pgn_line,
  }))
}

export async function loadCoachingBrief(): Promise<CoachingBrief> {
  const response = await fetch('/api/coach/brief')
  if (!response.ok) throw new Error(await readError(response, `Coaching brief failed (${response.status}).`))
  return (await response.json()) as CoachingBrief
}

export async function loadEndgameLessons(): Promise<{ eloTier: string | null; lessons: EndgameLesson[] }> {
  const response = await fetch('/api/lessons/endgames')
  if (!response.ok) throw new Error(await readError(response, `Endgame list failed (${response.status}).`))
  const body = (await response.json()) as { elo_tier?: string | null; lessons?: EndgameLessonJson[] }
  return {
    eloTier: body.elo_tier ?? null,
    lessons: (body.lessons ?? []).map(lesson => ({
      endgameType: lesson.endgame_type,
      fenFull: lesson.fen_full,
      humanMoveUci: lesson.human_move_uci,
      eloTier: lesson.elo_tier,
      pieceCount: lesson.piece_count,
    })),
  }
}
