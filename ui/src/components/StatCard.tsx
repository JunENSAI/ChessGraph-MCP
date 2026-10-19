import type { ReactNode } from 'react'
import { AnimatePresence, motion } from 'motion/react'
import { ChevronRight, type LucideIcon } from 'lucide-react'

interface StatCardProps {
  id: string
  icon: LucideIcon
  title: string
  headline: string
  caption: string
  expanded: boolean
  onToggle: (id: string) => void
  children: ReactNode
}

export function StatCard({ id, icon: Icon, title, headline, caption, expanded, onToggle, children }: StatCardProps) {
  return (
    <motion.article
      layout
      transition={{ layout: { duration: 0.28, ease: [0.2, 0.8, 0.2, 1] } }}
      className={`stat-card${expanded ? ' expanded' : ''}`}
    >
      <motion.button
        layout="position"
        type="button"
        className="stat-summary"
        aria-expanded={expanded}
        aria-controls={`${id}-details`}
        onClick={() => onToggle(id)}
      >
        <span className="stat-icon">
          <Icon size={16} />
        </span>
        <span className="stat-text">
          <span className="eyebrow">{title}</span>
          <strong>{headline}</strong>
          <span className="muted">{caption}</span>
        </span>
        <ChevronRight size={16} className="stat-chevron" />
      </motion.button>
      <AnimatePresence initial={false}>
        {expanded && (
          <motion.div
            id={`${id}-details`}
            className="stat-details"
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0, transition: { delay: 0.12, duration: 0.2 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </motion.article>
  )
}
