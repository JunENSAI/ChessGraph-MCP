import type { OpeningLesson } from './lessons'
import type { OutcomeCounts } from './types'

export interface OpeningVariant {
  lesson: OpeningLesson
  label: string
}

export interface OpeningFamily {
  name: string
  games: number
  /** Results summed over the variants, from the user's side. */
  results: OutcomeCounts
  variants: OpeningVariant[]
}

/** Win share in whole percent, or null without decided or drawn games. */
export function winPercent(results: OutcomeCounts): number | null {
  const total = results.wins + results.draws + results.losses
  return total ? Math.round((results.wins / total) * 100) : null
}

const PIECE_WORDS: Record<string, [string, string]> = {
  K: ['king', 'kings'],
  Q: ['queen', 'queens'],
  R: ['rook', 'rooks'],
  B: ['bishop', 'bishops'],
  N: ['knight', 'knights'],
  P: ['pawn', 'pawns'],
}

/**
 * Collapse book names onto one opening, and keep the rest as a variant.
 * London lines are named London System even when the database prefixes Queen's Pawn Game.
 */
export function openingFamilyName(name: string): { family: string; variant: string } {
  const trimmed = name.trim()
  if (/london/i.test(trimmed)) {
    const variant = trimmed
      .replace(/queen'?s pawn game:\s*/i, '')
      .replace(/london system/i, '')
      .replace(/^[:,\s-]+/, '')
      .replace(/[:,\s-]+$/g, '')
      .trim()
    return { family: 'London System', variant: variant || 'Main line' }
  }
  const colon = trimmed.indexOf(':')
  if (colon === -1) return { family: trimmed, variant: 'Main line' }
  return {
    family: trimmed.slice(0, colon).trim(),
    variant: trimmed.slice(colon + 1).trim() || 'Main line',
  }
}

/** Top families by games played. Variants inside a family stay selectable. */
export function groupOpenings(lessons: OpeningLesson[], limit = 5): OpeningFamily[] {
  const grouped = new Map<string, OpeningFamily>()
  for (const lesson of lessons) {
    const { family, variant } = openingFamilyName(lesson.openingName)
    const key = family.toLowerCase()
    const existing = grouped.get(key)
    const entry: OpeningVariant = { lesson, label: variant }
    if (!existing) {
      grouped.set(key, {
        name: family,
        games: lesson.games,
        results: { wins: lesson.wins, draws: lesson.draws, losses: lesson.losses },
        variants: [entry],
      })
    } else {
      existing.games += lesson.games
      existing.results.wins += lesson.wins
      existing.results.draws += lesson.draws
      existing.results.losses += lesson.losses
      existing.variants.push(entry)
    }
  }
  const families = [...grouped.values()]
  families.sort((a, b) => b.games - a.games || a.name.localeCompare(b.name))
  for (const family of families) {
    family.variants.sort((a, b) => b.lesson.games - a.lesson.games || a.label.localeCompare(b.label))
    // Two stored names can shorten to one label (London vs 1...d5 and vs 1...Nf6): add the ECO code.
    const seen = new Map<string, number>()
    for (const entry of family.variants) seen.set(entry.label, (seen.get(entry.label) ?? 0) + 1)
    for (const entry of family.variants) {
      if ((seen.get(entry.label) ?? 0) > 1) entry.label = `${entry.label} · ${entry.lesson.ecoCode ?? entry.lesson.openingName}`
    }
  }
  return families.slice(0, limit)
}

function sideLabel(code: string): string {
  const counts: Record<string, number> = {}
  for (const char of code) counts[char] = (counts[char] ?? 0) + 1
  const parts: string[] = []
  for (const piece of ['K', 'Q', 'R', 'B', 'N', 'P']) {
    const count = counts[piece] ?? 0
    if (!count) continue
    const [one, many] = PIECE_WORDS[piece]
    if (count === 1) parts.push(one)
    else if (count === 2) parts.push(`two ${many}`)
    else parts.push(`${count} ${many}`)
  }
  if (parts.length === 0) return 'king'
  if (parts.length === 1) return parts[0]
  return `${parts[0]} and ${parts.slice(1).join(' and ')}`
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Turn a material code such as KPPvKPP into a readable ending name. */
export function endgameTitle(code: string): string {
  const [left, right] = code.split(/v/i)
  if (!left || !right || /[^KQRBNPkqrbnp]/.test(left + right)) return code.replaceAll('_', ' ')
  return `${capitalize(sideLabel(left))} vs ${sideLabel(right)}`
}
