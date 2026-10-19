import { useState } from 'react'
import { motion } from 'motion/react'
import { Crown, Flag, Shield, Swords, Trophy } from 'lucide-react'
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
import { RATING_BANDS } from '../data/demo'
import type { OpeningStat, RatingBand } from '../data/types'
import { combine, share, totalGames, winRate } from '../lib/stats'

const AXIS = { fill: '#8d96a5', fontSize: 11 }
const GRID = '#232a35'
const TOOLTIP = {
  contentStyle: { background: '#151922', border: '1px solid #343c49', borderRadius: 8, fontSize: 12 },
  labelStyle: { color: '#f3f5f7' },
  cursor: { fill: 'rgba(255,255,255,0.04)' },
}
const COLORS = { win: '#b8f05a', draw: '#8d96a5', loss: '#ff7b72', white: '#f3f5f7', black: '#77a7ff' }

function repertoireRows(items: OpeningStat[]) {
  return items.map(item => ({
    name: item.name,
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
            <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={120} />
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
            <tr key={row.name}>
              <td>{row.name}</td>
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

function ColorResultsChart({ band }: { band: RatingBand }) {
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

function EndgamePatternChart({ band }: { band: RatingBand }) {
  const rows = band.endgames.map(item => ({
    name: item.label,
    'With White': totalGames(item.white),
    'With Black': totalGames(item.black),
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} layout="vertical" margin={{ left: 12, right: 16 }}>
          <CartesianGrid stroke={GRID} horizontal={false} />
          <XAxis type="number" tick={AXIS} axisLine={false} tickLine={false} allowDecimals={false} />
          <YAxis type="category" dataKey="name" tick={AXIS} axisLine={false} tickLine={false} width={150} />
          <Tooltip {...TOOLTIP} />
          <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
          <Bar dataKey="With White" stackId="e" fill={COLORS.white} />
          <Bar dataKey="With Black" stackId="e" fill={COLORS.black} radius={[0, 4, 4, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

function EndgameWinChart({ band }: { band: RatingBand }) {
  const rows = band.endgames.map(item => ({
    name: item.label,
    White: winRate(item.white),
    Black: winRate(item.black),
  }))
  return (
    <div className="chart">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={rows} margin={{ right: 12 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis dataKey="name" tick={AXIS} axisLine={false} tickLine={false} interval={0} />
          <YAxis domain={[0, 100]} unit="%" tick={AXIS} axisLine={false} tickLine={false} width={44} />
          <Tooltip {...TOOLTIP} formatter={value => `${value}%`} />
          <Legend wrapperStyle={{ fontSize: 11 }} itemSorter={null} />
          <Bar dataKey="White" fill={COLORS.white} radius={[4, 4, 0, 0]} />
          <Bar dataKey="Black" fill={COLORS.black} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}

export function RecapView() {
  const [bandId, setBandId] = useState(RATING_BANDS[1].id)
  const [expanded, setExpanded] = useState<string | null>(null)
  const band = RATING_BANDS.find(item => item.id === bandId)!

  const toggle = (id: string) => setExpanded(current => (current === id ? null : id))
  const whiteTotal = totalGames(band.white)
  const blackTotal = totalGames(band.black)
  const topOpening = [...band.openingsWhite].sort((a, b) => totalGames(b.results) - totalGames(a.results))[0]
  const topDefense = [...band.defensesBlack].sort((a, b) => totalGames(b.results) - totalGames(a.results))[0]
  const frequentEndgame = [...band.endgames].sort(
    (a, b) => totalGames(combine(b.white, b.black)) - totalGames(combine(a.white, a.black)),
  )[0]
  const endgameTotals = combine(...band.endgames.flatMap(item => [item.white, item.black]))
  const endgameWhite = combine(...band.endgames.map(item => item.white))
  const endgameBlack = combine(...band.endgames.map(item => item.black))

  return (
    <div className="view recap-view">
      <header className="recap-head">
        <div>
          <h2 className="recap-title">Rating-band recap</h2>
          <p className="panel-subtitle">
            Select a card to see its statistics · demo profile until the Postgres MCP is connected
          </p>
        </div>
        <div className="band-switch" role="tablist" aria-label="Rating band">
          {RATING_BANDS.map(item => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={item.id === bandId}
              className={item.id === bandId ? 'active' : ''}
              onClick={() => setBandId(item.id)}
            >
              {item.id === bandId && <motion.span layoutId="band-indicator" className="band-indicator" />}
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
          <span className="eyebrow">Endgame win rate</span>
          <strong>{winRate(endgameTotals)}%</strong>
        </div>
      </div>

      <motion.div layout className="card-grid" key={bandId}>
        <StatCard
          id="openings"
          icon={Swords}
          title="Favorite openings · White"
          headline={topOpening.name}
          caption={`${share(totalGames(topOpening.results), whiteTotal)}% of White games · ${winRate(topOpening.results)}% wins`}
          expanded={expanded === 'openings'}
          onToggle={toggle}
        >
          <RepertoireChart items={band.openingsWhite} />
        </StatCard>
        <StatCard
          id="defenses"
          icon={Shield}
          title="Defenses · Black"
          headline={topDefense.name}
          caption={`${share(totalGames(topDefense.results), blackTotal)}% of Black games · ${winRate(topDefense.results)}% wins`}
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
          id="patterns"
          icon={Flag}
          title="Endgame patterns"
          headline={frequentEndgame.label}
          caption={`Most frequent · ${totalGames(combine(frequentEndgame.white, frequentEndgame.black))} games`}
          expanded={expanded === 'patterns'}
          onToggle={toggle}
        >
          <EndgamePatternChart band={band} />
        </StatCard>
        <StatCard
          id="endgame-wins"
          icon={Crown}
          title="Endgame win rate"
          headline={`${winRate(endgameWhite)}% · ${winRate(endgameBlack)}%`}
          caption="White pieces · Black pieces"
          expanded={expanded === 'endgame-wins'}
          onToggle={toggle}
        >
          <EndgameWinChart band={band} />
        </StatCard>
      </motion.div>
    </div>
  )
}
