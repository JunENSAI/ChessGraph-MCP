import { Suspense, lazy, useState } from 'react'
import { motion } from 'motion/react'
import { ChartColumn, FolderOpen, GraduationCap, type LucideIcon } from 'lucide-react'
import { GamesView } from './views/GamesView'
import { TrainingView } from './views/TrainingView'

const RecapView = lazy(() => import('./views/RecapView').then(module => ({ default: module.RecapView })))

type Mode = 'training' | 'games' | 'recap'

const MODES: { id: Mode; label: string; icon: LucideIcon }[] = [
  { id: 'training', label: 'Training', icon: GraduationCap },
  { id: 'games', label: 'My games', icon: FolderOpen },
  { id: 'recap', label: 'Recap', icon: ChartColumn },
]

export default function App() {
  const [mode, setMode] = useState<Mode>('training')
  const [visited, setVisited] = useState<Set<Mode>>(() => new Set(['training']))

  const open = (next: Mode) => {
    setMode(next)
    setVisited(current => (current.has(next) ? current : new Set(current).add(next)))
  }

  return (
    <div className="app" data-theme="dark">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">
            ♞
          </span>
          <div>
            <h1 className="brand-name">ChessGraph Coach</h1>
            <p className="brand-tagline">Stockfish evidence · personal games · Hermes explanations</p>
          </div>
        </div>
        <nav className="mode-switch" aria-label="Coach mode">
          {MODES.map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              className={mode === id ? 'active' : ''}
              aria-current={mode === id ? 'page' : undefined}
              onClick={() => open(id)}
            >
              {mode === id && <motion.span layoutId="mode-indicator" className="mode-indicator" />}
              <Icon size={15} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
        <span className="demo-badge">Demo data</span>
      </header>

      <main className="workspace">
        <div hidden={mode !== 'training'} className="view-slot">
          <TrainingView />
        </div>
        <div hidden={mode !== 'games'} className="view-slot">
          <GamesView active={mode === 'games'} />
        </div>
        <div hidden={mode !== 'recap'} className="view-slot">
          {visited.has('recap') && (
            <Suspense fallback={<p className="muted small">Loading recap…</p>}>
              <RecapView />
            </Suspense>
          )}
        </div>
      </main>
    </div>
  )
}
