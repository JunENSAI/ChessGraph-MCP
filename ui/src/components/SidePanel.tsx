import type { ReactNode } from 'react'
import type { LucideIcon } from 'lucide-react'

export interface SideTab<Id extends string> {
  id: Id
  label: string
  icon: LucideIcon
  badge?: string | number
  content: ReactNode
}

interface SidePanelProps<Id extends string> {
  label: string
  tabs: SideTab<Id>[]
  active: Id
  onChange: (id: Id) => void
}

/**
 * One tabbed panel beside the board. Every tab stays mounted, so the coach
 * thread, the explorer and scroll positions survive switching tabs.
 */
export function SidePanel<Id extends string>({ label, tabs, active, onChange }: SidePanelProps<Id>) {
  return (
    <section className="panel side-panel" aria-label={label}>
      <div className="side-tabs" role="tablist" aria-label={label}>
        {tabs.map(tab => {
          const Icon = tab.icon
          const selected = tab.id === active
          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${label}-${tab.id}`}
              aria-selected={selected}
              aria-controls={`panel-${label}-${tab.id}`}
              className={`side-tab${selected ? ' active' : ''}`}
              onClick={() => onChange(tab.id)}
            >
              <Icon size={14} />
              <span>{tab.label}</span>
              {tab.badge !== undefined && <span className="tab-badge">{tab.badge}</span>}
            </button>
          )
        })}
      </div>
      {tabs.map(tab => (
        <div
          key={tab.id}
          role="tabpanel"
          id={`panel-${label}-${tab.id}`}
          aria-labelledby={`tab-${label}-${tab.id}`}
          className="side-body"
          hidden={tab.id !== active}
        >
          {tab.content}
        </div>
      ))}
    </section>
  )
}
