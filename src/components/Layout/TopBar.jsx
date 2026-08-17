import { int, pct } from '../../utils/dataTransforms'

/**
 * Top bar. Mirrors the original's panel_title ("Course Dependency & Program Analytics")
 * over the Northeastern red header treatment from app.css, and carries the synthetic-data
 * notice where it is visible without being intrusive.
 */
export default function TopBar({ summary, onToggleSidebar, sidebarOpen }) {
  const k = summary?.kpis

  return (
    <header className="sticky top-0 z-30 border-b border-nu-gray-200 bg-nu-white">
      <div className="flex items-stretch">
        {/* Red bar with black left edge — the original's .panel-title treatment */}
        <div className="flex items-center gap-3 border-l-[6px] border-nu-black bg-nu-red px-4 py-3">
          <button
            type="button"
            onClick={onToggleSidebar}
            aria-label={sidebarOpen ? 'Collapse filters' : 'Expand filters'}
            aria-expanded={sidebarOpen}
            className="rounded p-1 text-nu-white/90 transition hover:bg-nu-white/15 hover:text-nu-white"
          >
            <svg width="18" height="18" viewBox="0 0 20 20" fill="none" aria-hidden="true">
              <path
                d="M3 5h14M3 10h14M3 15h14"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
              />
            </svg>
          </button>
          <div>
            <h1 className="text-[0.95rem] font-black leading-tight tracking-tight text-nu-white">
              Course Dependency &amp; Program Analytics
            </h1>
            <p className="text-[0.7rem] leading-tight text-nu-white/80">
              Office of the University Registrar · Pacific Ridge University
            </p>
          </div>
        </div>

        {/* KPI strip */}
        <div className="hidden flex-1 items-center justify-end gap-6 px-5 lg:flex">
          {k ? (
            <>
              <Kpi label="Courses" value={int(k.total_courses)} />
              <Kpi label="Programs" value={int(k.total_programs)} />
              <Kpi label="Sections" value={int(k.total_sections)} />
              <Kpi
                label="At capacity"
                value={`${k.pct_at_capacity}%`}
                tone={k.pct_at_capacity >= 35 ? 'bad' : 'default'}
              />
              <Kpi
                label="Waitlisted"
                value={`${k.pct_with_waitlist}%`}
                tone={k.pct_with_waitlist >= 30 ? 'warn' : 'default'}
              />
              <Kpi label="Bottlenecks" value={int(k.bottleneck_courses)} tone="bad" />
            </>
          ) : (
            <span className="text-[0.75rem] text-muted">Loading indicators…</span>
          )}
        </div>

        <div className="flex items-center px-4">
          <span className="chip border border-nu-gold/60 bg-nu-gold/15 text-nu-gray-900">
            <svg width="11" height="11" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true">
              <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 12H9v-2h2v2zm0-3H9V6h2v5z" />
            </svg>
            Synthetic data
          </span>
        </div>
      </div>
    </header>
  )
}

function Kpi({ label, value, tone = 'default' }) {
  const toneClass =
    tone === 'bad'
      ? 'text-bad'
      : tone === 'warn'
        ? 'text-nu-gray-900'
        : 'text-nu-gray-900'
  return (
    <div className="text-right">
      <div className={`text-[0.95rem] font-black leading-none tabular-nums ${toneClass}`}>
        {value}
      </div>
      <div className="mt-0.5 text-[0.65rem] font-bold uppercase tracking-wide text-muted">
        {label}
      </div>
    </div>
  )
}
