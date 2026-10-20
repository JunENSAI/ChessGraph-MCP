import { useEffect, useState } from 'react'
import { motion } from 'motion/react'
import { Shield, Swords, Timer, Trophy } from 'lucide-react'
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { StatCard } from '../components/StatCard'
import { busiestBand, clockGameCounts, loadRecap, mostPlayedClock, mostPlayedLine } from '../data/recap'
import type { OpeningStat, RecapBand, RecapPayload, TimeControlStat } from '../data/types'
import { share, totalGames, winRate } from '../lib/stats'

const AXIS = { fill: '#8d96a5', fontSize: 11 }
const GRID = '#232a35'
const TOOLTIP = {
  contentStyle: { background: '#151922', border: '1px solid #343c49', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#f3f5f7' },
  cursor: { fill: 'rgba(255,255,255,0.04)' },
}
const COLORS = { win: '#b8f05a', draw: '#8d96a5', loss: '#ff7b72' }

function repertoireRows(items: OpeningStat[]) {
  return items.map(item => ({
    name: item.name,
    fullName: item.name,
    eco: item.eco,
    Wins: item.results.wins,
    Draws: item.results.draws,
    Losses: item.results.losses,
    winRate: winRate(item.results),
  }))
}

function RepertoireChart({ items }: { items: OpeningStat[] }) {
  const rows = repertoireRows(items)
  return (
    <>
      <div className="chart">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 12, right: 16 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={190} />
            <Tooltip {...TOOLTIP} />
            <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
            <Bar dataKey="Wins" stackId="r" fill={COLORS.win} radius={[4, 0, 0, 4]} />
            <Bar dataKey="Draws" stackId="r" fill={COLORS.draw} />
            <Bar dataKey="Losses" stackId="r" fill={COLORS.loss} radius={[0, 4, 4, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="stat-table">
        <thead>
          <tr>
            <th>Opening</th>
            <th>ECO</th>
            <th>Games</th>
            <th>Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={`${row.fullName}-${row.eco}`}>
              <td>{row.fullName}</td>
              <td>{row.eco}</td>
              <td>{row.Wins + row.Draws + row.Losses}</td>
              <td>{row.winRate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function ColorResultsChart({ band }: { band: RecapBand }) {
  const rows = (['white', 'black'] as const).map(color => {
    const counts = band[color]
    const total = totalGames(counts)
    return {
      name: color === 'white' ? 'White pieces' : 'Black pieces',
      Wins: share(counts.wins, total),
      Draws: share(counts.draws, total),
      Losses: share(counts.losses, total),
      games: total,
    }
  })
  return (
    <>
      <div className="chart short">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 12, right: 16 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" domain={[0, 100]} unit="%" tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={100} />
            <Tooltip {...TOOLTIP} formatter={value => `${value}%`} />
            <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
            <Bar dataKey="Wins" stackId="c" fill={COLORS.win} />
            <Bar dataKey="Draws" stackId="c" fill={COLORS.draw} />
            <Bar dataKey="Losses" stackId="c" fill={COLORS.loss} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="muted small">
        {rows[0].games} games with White · {rows[1].games} games with Black
      </p>
    </>
  )
}

function TimeControlChart({ items }: { items: TimeControlStat[] }) {
  const rows = items.map(item => ({
    name: item.label,
    Wins: item.results.wins,
    Draws: item.results.draws,
    Losses: item.results.losses,
    winRate: winRate(item.results),
    games: totalGames(item.results),
  }))
  return (
    <>
      <div className="chart short">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} layout="vertical" margin={{ left: 12, right: 16 }}>
            <CartesianGrid stroke={GRID} horizontal={false} />
            <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={80} />
            <Tooltip {...TOOLTIP} />
            <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
            <Bar dataKey="Wins" stackId="t" fill={COLORS.win} />
            <Bar dataKey="Draws" stackId="t" fill={COLORS.draw} />
            <Bar dataKey="Losses" stackId="t" fill={COLORS.loss} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <table className="stat-table">
        <thead>
          <tr>
            <th>Time control</th>
            <th>Games</th>
            <th>Win rate</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.name}>
              <td>{row.name}</td>
              <td>{row.games}</td>
              <td>{row.winRate}%</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  )
}

function BandClockChart({ band }: { band: RecapBand }) {
  const rows = clockGameCounts(band)
  if (rows.length === 0) return <p className="muted small">No games in this band.</p>
  return (
    <div className="chart short">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ left: 0, right: 8, top: 8 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="label" tick={AXIS} axisLine={false} tickLine={false} />
          <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} width={36} />
          <Tooltip {...TOOLTIP} />
          <Bar dataKey="games" name="Games" fill={COLORS.win} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function ClockProfileChart({ clock }: { clock: TimeControlStat | undefined }) {
  if (!clock) return <p className="muted small">No time control in this band.</p>
  const results = [
    { name: 'Wins', value: clock.results.wins },
    { name: 'Draws', value: clock.results.draws },
    { name: 'Losses', value: clock.results.losses },
  ]
  const elos = [
    { name: 'Opponent', value: clock.averageOpponentElo },
    { name: 'When you win', value: clock.averageEloWhenWin },
    { name: 'When you lose', value: clock.averageEloWhenLoss },
  ].filter(item => item.value != null)
  return (
    <>
      <div className="chart short">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={results} margin={{ left: 0, right: 8, top: 8 }}>
            <CartesianGrid stroke={GRID} vertical={false} />
            <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} />
            <YAxis tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} width={36} />
            <Tooltip {...TOOLTIP} />
            <Bar dataKey="value" name="Games" fill="#77a7ff" radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      {elos.length > 0 ? (
        <div className="chart short">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={elos} margin={{ left: 0, right: 8, top: 8 }}>
              <CartesianGrid stroke={GRID} vertical={false} />
              <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} />
              <YAxis tick={AXIS} axisLine={false} tickLine={false} width={40} />
              <Tooltip {...TOOLTIP} />
              <Bar dataKey="value" name="Elo" fill={COLORS.draw} radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <p className="muted small">Elo is not stored for this time control.</p>
      )}
    </>
  )
}

function lineCaption(line: OpeningStat | undefined, sideTotal: number): string {
  if (!line || sideTotal === 0) return 'No games in this band'
  return `${share(totalGames(line.results), sideTotal)}% of games with these pieces · ${winRate(line.results)}% wins`
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
        <h2 className="recap-title">Rating-band recap</h2>
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
  const [expanded, setExpanded] = useState<string | null>(null)
  const band = payload.bands.find(item => item.id === bandId) ?? initial

  if (!band) {
    return (
      <div className="view recap-view">
        <h2 className="recap-title">Rating-band recap</h2>
        <p className="panel-subtitle">No games are stored for these rating bands.</p>
      </div>
    )
  }

  const toggle = (id: string) => setExpanded(current => (current === id ? null : id))
  const whiteTotal = totalGames(band.white)
  const blackTotal = totalGames(band.black)
  const topOpening = mostPlayedLine(band.openingsWhite)
  const topDefense = mostPlayedLine(band.defensesBlack)
  const topClock = mostPlayedClock(band)

  return (
    <div className="view recap-view">
      <header className="recap-head">
        <div>
          <h2 className="recap-title">Rating-band recap</h2>
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
          <strong>{topClock ? topClock.label : '—'}</strong>
        </div>
      </div>

      <div className="insight-grid">
        <article className="stat-card expanded">
          <div className="stat-summary insight-head">
            <span className="stat-text">
              <span className="eyebrow">Games in band</span>
              <strong>{whiteTotal + blackTotal}</strong>
              <span className="muted">Games in each time control</span>
            </span>
          </div>
          <div className="stat-details">
            <BandClockChart band={band} />
          </div>
        </article>
        <article className="stat-card expanded">
          <div className="stat-summary insight-head">
            <span className="stat-text">
              <span className="eyebrow">Most played clock</span>
              <strong>{topClock ? topClock.label : '—'}</strong>
              <span className="muted">Results and average Elo</span>
            </span>
          </div>
          <div className="stat-details">
            <ClockProfileChart clock={topClock} />
          </div>
        </article>
      </div>

      <motion.div layout className="card-grid" key={band.id}>
        <StatCard
          id="openings"
          icon={Swords}
          title="Most played lines · White"
          headline={topOpening?.name ?? 'No games'}
          caption={lineCaption(topOpening, whiteTotal)}
          expanded={expanded === 'openings'}
          onToggle={toggle}
        >
          <RepertoireChart items={band.openingsWhite} />
        </StatCard>
        <StatCard
          id="defenses"
          icon={Shield}
          title="Most played lines · Black"
          headline={topDefense?.name ?? 'No games'}
          caption={lineCaption(topDefense, blackTotal)}
          expanded={expanded === 'defenses'}
          onToggle={toggle}
        >
          <RepertoireChart items={band.defensesBlack} />
        </StatCard>
        <StatCard
          id="colors"
          icon={Trophy}
          title="Win percentage by color"
          headline={`${winRate(band.white)}% · ${winRate(band.black)}%`}
          caption="White pieces · Black pieces"
          expanded={expanded === 'colors'}
          onToggle={toggle}
        >
          <ColorResultsChart band={band} />
        </StatCard>
        <StatCard
          id="clocks"
          icon={Timer}
          title="Results by time control"
          headline={topClock ? `${topClock.label} · ${totalGames(topClock.results)}` : 'No games'}
          caption={topClock ? `${winRate(topClock.results)}% wins in that time control` : 'No stored games'}
          expanded={expanded === 'clocks'}
          onToggle={toggle}
        >
          <TimeControlChart items={band.timeControls} />
        </StatCard>
      </motion.div>
      <p className="muted small recap-note">
        Win rate counts draws as non-wins. Endgame types are not stored on these games, so this recap does not show them.
      </p>
    </div>
  )
}
