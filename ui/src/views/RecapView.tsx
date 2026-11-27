import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { ScoreBar, ScoreLegend } from '../components/ScoreBar'
import { busiestBand, chartLabel, loadRecap, mostPlayedClock, topLines } from '../data/recap'
import type { OpeningStat, OutcomeCounts, RecapBand, RecapPayload } from '../data/types'
import { totalGames, winRate } from '../lib/stats'

interface ResultRow {
  id: string
  label: string
  counts: OutcomeCounts
  elo?: number | null
}

function ResultRows({ title, rows }: { title: string; rows: ResultRow[] }) {
  return (
    <>
      <tr className="score-group">
        <th colSpan={5} scope="colgroup">
          {title}
        </th>
      </tr>
      {rows.map(row => (
        <tr key={row.id}>
          <th scope="row">{row.label}</th>
          <td className="num">{totalGames(row.counts)}</td>
          <td className="bar-cell">
            <ScoreBar {...row.counts} label={row.label} />
          </td>
          <td className="num">{winRate(row.counts)}%</td>
          <td className="num muted">{row.elo ? Math.round(row.elo) : '—'}</td>
        </tr>
      ))}
    </>
  )
}

function ResultsCard({ band }: { band: RecapBand }) {
  const colors: ResultRow[] = [
    { id: 'white', label: 'With White', counts: band.white },
    { id: 'black', label: 'With Black', counts: band.black },
  ]
  const clocks: ResultRow[] = band.timeControls
    .filter(item => totalGames(item.results) > 0)
    .sort((a, b) => totalGames(b.results) - totalGames(a.results))
    .map(item => ({ id: item.id, label: item.label, counts: item.results, elo: item.averageOpponentElo }))
  return (
    <section className="recap-card" aria-labelledby="results-title">
      <header className="recap-card-head">
        <div>
          <h3 id="results-title">Results</h3>
          <p className="muted small">By color and by time control, in this band.</p>
        </div>
        <ScoreLegend />
      </header>
      <table className="score-table">
        <thead>
          <tr>
            <th scope="col" />
            <th scope="col" className="num">Games</th>
            <th scope="col">Wins · draws · losses</th>
            <th scope="col" className="num">Win %</th>
            <th scope="col" className="num">Opp. Elo</th>
          </tr>
        </thead>
        <tbody>
          <ResultRows title="By color" rows={colors} />
          {clocks.length > 0 && <ResultRows title="By time control" rows={clocks} />}
        </tbody>
      </table>
    </section>
  )
}

function RepertoireCard({ title, side, items, sideTotal }: { title: string; side: string; items: OpeningStat[]; sideTotal: number }) {
  const lines = topLines(items, 6)
  return (
    <section className="recap-card" aria-label={title}>
      <header className="recap-card-head">
        <div>
          <h3>{title}</h3>
          <p className="muted small">
            Your most played lines {side} · {sideTotal} games
          </p>
        </div>
      </header>
      {lines.length === 0 ? (
        <p className="muted small">No games with these pieces in this band.</p>
      ) : (
        <ol className="repertoire-list">
          {lines.map(line => {
            // The family shows under the line only when the name has a variation after it.
            const family = line.name.includes(':') ? line.name.split(':')[0].trim() : null
            const games = totalGames(line.results)
            return (
              <li key={`${line.name}-${line.eco}`}>
                <div className="repertoire-name">
                  <strong title={line.name}>{chartLabel(line.name, line.eco)}</strong>
                  {family && <span className="muted small">{family}</span>}
                </div>
                <span className="num">{games}</span>
                <ScoreBar {...line.results} label={line.name} />
                <span className="num">{winRate(line.results)}%</span>
              </li>
            )
          })}
        </ol>
      )}
    </section>
  )
}

export function RecapView() {
  const [payload, setPayload] = useState<RecapPayload | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    let active = true
    setPayload(null)
    setError(null)
    loadRecap()
      .then(next => {
        if (active) setPayload(next)
      })
      .catch((reason: unknown) => {
        if (active) setError(reason instanceof Error ? reason.message : 'The recap could not be loaded.')
      })
    return () => {
      active = false
    }
  }, [attempt])

  if (error) {
    return (
      <div className="view recap-view">
        <h2 className="recap-title">Home</h2>
        <p className="panel-subtitle">{error}</p>
        <button type="button" onClick={() => setAttempt(current => current + 1)}>
          Try again
        </button>
      </div>
    )
  }

  if (!payload) {
    return (
      <div className="view recap-view">
        <p className="muted small">Reading your games…</p>
      </div>
    )
  }

  return <RecapBands payload={payload} />
}

function RecapBands({ payload }: { payload: RecapPayload }) {
  const initial = busiestBand(payload.bands)
  const [bandId, setBandId] = useState(initial?.id ?? '')
  const band = payload.bands.find(item => item.id === bandId) ?? initial

  if (!band) {
    return (
      <div className="view recap-view">
        <h2 className="recap-title">Home</h2>
        <p className="panel-subtitle">No games are stored for these rating bands.</p>
      </div>
    )
  }

  const whiteTotal = totalGames(band.white)
  const blackTotal = totalGames(band.black)
  const topClock = mostPlayedClock(band)

  return (
    <div className="view recap-view">
      <header className="recap-head">
        <div>
          <h2 className="recap-title">Rating-band recap</h2>
          <p className="panel-subtitle">
            {payload.gameCount} stored games · results and repertoire by rating band.
          </p>
        </div>
        <div className="band-switch" role="tablist" aria-label="Rating band">
          {payload.bands.map(item => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={item.id === band.id}
              className={item.id === band.id ? 'active' : ''}
              onClick={() => setBandId(item.id)}
            >
              {item.id === band.id && <motion.span layoutId="band-indicator" className="band-indicator" />}
              <span>{item.label}</span>
            </button>
          ))}
        </div>
      </header>

      <div className="summary-strip">
        <div>
          <span className="eyebrow">Games in band</span>
          <strong>{whiteTotal + blackTotal}</strong>
        </div>
        <div>
          <span className="eyebrow">Win rate · White</span>
          <strong>{winRate(band.white)}%</strong>
        </div>
        <div>
          <span className="eyebrow">Win rate · Black</span>
          <strong>{winRate(band.black)}%</strong>
        </div>
        <div>
          <span className="eyebrow">Most played clock</span>
          <strong>{topClock && totalGames(topClock.results) > 0 ? topClock.label : '—'}</strong>
        </div>
      </div>

      <motion.div className="recap-body" key={band.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
        <ResultsCard band={band} />
        <div className="recap-columns">
          <RepertoireCard title="Repertoire · White" side="with White" items={band.openingsWhite} sideTotal={whiteTotal} />
          <RepertoireCard title="Repertoire · Black" side="with Black" items={band.defensesBlack} sideTotal={blackTotal} />
        </div>
      </motion.div>
      <p className="muted small recap-note">
        Win rate counts draws as non-wins. Hover a bar for its counts. Endgame types are not stored on these games, so
        this recap does not show them.
      </p>
    </div>
  )
}
