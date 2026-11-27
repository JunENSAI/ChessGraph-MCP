import { ChevronRight } from 'lucide-react'
import { winPercent, type OpeningFamily } from '../data/openings'
import { ScoreBar } from './ScoreBar'

interface RepertoireListProps {
  title: string
  note: string
  /** True while one of these lines is on the board. */
  active: boolean
  family: string
  families: OpeningFamily[]
  variant: string
  /** Drill the main line of a family. */
  onFamily: (name: string) => void
  /** Drill one variant by its stored opening name. */
  onVariant: (openingName: string) => void
  empty: string
}

function share(value: number | null): string {
  return value === null ? '—' : `${value}%`
}

/** Your openings for one colour: games, results and the variants of the chosen family. A click drills the line. */
export function RepertoireList({ title, note, active, family, families, variant, onFamily, onVariant, empty }: RepertoireListProps) {
  return (
    <section className={`track-card repertoire-card${active ? ' active' : ''}`} aria-label={title}>
      <div className="repertoire-card-head">
        <span className="eyebrow">{title}</span>
        <span className="muted small">games · W/D/L · win</span>
      </div>
      {families.length === 0 && <span>{empty}</span>}
      <ul className="family-list">
        {families.map(item => {
          const open = item.name === family
          const rate = winPercent(item.results)
          return (
            <li key={item.name} className={open ? 'open' : undefined}>
              <button type="button" className="family-row" aria-expanded={open} onClick={() => onFamily(item.name)}>
                <ChevronRight size={13} className="family-caret" aria-hidden />
                <span className="family-name">{item.name}</span>
                <span className="num">{item.games}</span>
                <ScoreBar {...item.results} label={item.name} />
                <span className="num">{share(rate)}</span>
              </button>
              {open && item.variants.length > 1 && (
                <ul className="variant-list">
                  {item.variants.map(entry => {
                    const lesson = entry.lesson
                    const current = active && lesson.openingName === variant
                    return (
                      <li key={lesson.openingName}>
                        <button
                          type="button"
                          className={`variant-row${current ? ' current' : ''}`}
                          aria-pressed={current}
                          onClick={() => onVariant(lesson.openingName)}
                        >
                          <span className="family-name">{entry.label}</span>
                          <span className="num">{lesson.games}</span>
                          <ScoreBar wins={lesson.wins} draws={lesson.draws} losses={lesson.losses} label={entry.label} />
                          <span className="num">{share(winPercent(lesson))}</span>
                        </button>
                      </li>
                    )
                  })}
                </ul>
              )}
            </li>
          )
        })}
      </ul>
      <span>{note}</span>
    </section>
  )
}
