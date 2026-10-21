import { Suspense, lazy, useState } from 'react'
import { motion } from 'motion/react'
import { FolderOpen, GraduationCap, House, type LucideIcon } from 'lucide-react'
import { GamesView } from './views/GamesView'
import { TrainingView } from './views/TrainingView'
import { DEFAULT_MODE, MODES, type Mode } from './lib/modes'

const RecapView = lazy(() => import('./views/RecapView').then(module => ({ default: module.RecapView })))

const ICONS: Record<Mode, LucideIcon> = {
  recap: House,
  training: GraduationCap,
  games: FolderOpen,
}

export default function App() {
  const [mode, setMode] = useState<Mode>(DEFAULT_MODE)
  const [visited, setVisited] = useState<Set<Mode>>(() => new Set([DEFAULT_MODE]))

  const open = (next: Mode) => {
    setMode(next)
    setVisited(current => (current.has(next) ? current : new Set(current).add(next)))
  }

  return (
    <div className="app" data-theme="dark">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark" aria-hidden="true">♞</span>
          <h1 className="brand-name">ChessGraph Coach</h1>
        </div>
        <nav className="mode-switch" aria-label="Coach mode">
          {MODES.map(({ id, label }) => {
            const Icon = ICONS[id]
            return (
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
            )
          })}
        </nav>
      </header>

      <main className="workspace">
        <div hidden={mode !== 'recap'} className="view-slot">
          {visited.has('recap') && (
            <Suspense fallback={<p className="muted small">Reading your games…</p>}>
              <RecapView />
            </Suspense>
          )}
        </div>
        <div hidden={mode !== 'training'} className="view-slot">
          <TrainingView />
        </div>
        <div hidden={mode !== 'games'} className="view-slot">
          <GamesView active={mode === 'games'} />
        </div>
      </main>
    </div>
  )
}
