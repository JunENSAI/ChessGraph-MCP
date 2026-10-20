import { Chess } from 'chess.js'
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

export function lineFromUci(uciLine: string, maxPlies = LESSON_PLIES): TrainingStep[] {
  const chess = new Chess()
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
    title: lesson.endgameType.replaceAll('_', ' '),
    detail: applied
      ? `${lesson.pieceCount} pieces · ${lesson.eloTier ?? 'stored position'}`
      : 'The stored technique move is not legal in this position.',
    userColor,
    startFen: lesson.fenFull,
    line,
    engineAfter: true,
    enginePlay: line.length === 0,
    missingLine: false,
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
  const response = await fetch(`/api/lessons/openings?color=${color}`)
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
