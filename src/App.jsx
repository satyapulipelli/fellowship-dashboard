import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import TopBar from './components/Layout/TopBar'
import Sidebar from './components/Layout/Sidebar'
import Disclaimer from './components/shared/Disclaimer'
import { Skeleton, ErrorState } from './components/shared/States'
import { useData, loadFile, peek } from './hooks/useData'
import { useFilters } from './hooks/useFilters'
import { DEFAULT_TAB, getTab } from './tabs/registry'

const tabs = {
  executive_summary: lazy(() => import('./tabs/ExecutiveSummary')),
  graph_view: lazy(() => import('./tabs/GraphView')),
  program_metrics: lazy(() => import('./tabs/ProgramMetrics')),
  course_metrics: lazy(() => import('./tabs/CourseMetrics')),
  redundancy_analysis: lazy(() => import('./tabs/RedundancyAnalysis')),
  demand_forecast: lazy(() => import('./tabs/DemandForecast')),
  temporal_analysis: lazy(() => import('./tabs/TemporalAnalysis')),
  term_correlation: lazy(() => import('./tabs/TermCorrelation')),
}

const MD_BREAKPOINT = 768

function useMediaQuery(query) {
  const [matches, setMatches] = useState(() =>
    typeof window !== 'undefined' ? window.matchMedia(query).matches : true,
  )
  useEffect(() => {
    const mql = window.matchMedia(query)
    const handler = (e) => setMatches(e.matches)
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [query])
  return matches
}

export default function App() {
  const [activeTab, setActiveTab] = useState(DEFAULT_TAB)
  const isDesktop = useMediaQuery(`(min-width: ${MD_BREAKPOINT}px)`)
  const [sidebarOpen, setSidebarOpen] = useState(isDesktop)
  const mainRef = useRef(null)
  const [tabKey, setTabKey] = useState(0)

  useEffect(() => {
    setSidebarOpen(isDesktop)
  }, [isDesktop])

  const { data: coreData, loading: coreLoading, error: coreError, reload: coreReload } =
    useData(['summary_stats.json', 'terms.json', 'programs.json', 'department_metrics.json'])

  const { data: enrollData } = useData(['enrollment_by_course.json'])

  const departmentNames = useMemo(() => {
    if (!coreData.department_metrics) return {}
    const out = {}
    for (const [code, d] of Object.entries(coreData.department_metrics))
      out[code] = d.name
    return out
  }, [coreData.department_metrics])

  const departmentCodes = useMemo(
    () => (coreData.department_metrics ? Object.keys(coreData.department_metrics).sort() : []),
    [coreData.department_metrics],
  )

  const courseTerms = useMemo(() => {
    if (!enrollData.enrollment_by_course || !coreData.terms) return null
    const termList = coreData.terms.published.map((t) => t.code)
    const termIdx = new Map(termList.map((t, i) => [t, i]))
    const offered = {}
    for (const [code, entry] of Object.entries(enrollData.enrollment_by_course)) {
      const idxs = []
      for (const t of entry.enrollment_series?.terms || [])
        if (termIdx.has(t)) idxs.push(termIdx.get(t))
      if (idxs.length) offered[code] = idxs
    }
    return { terms: termList, offered }
  }, [enrollData.enrollment_by_course, coreData.terms])

  const filters = useFilters({
    programs: coreData.programs,
    courseTerms,
    departments: departmentCodes,
  })

  const toggleSidebar = useCallback(() => setSidebarOpen((v) => !v), [])

  const handleSelectTab = useCallback((id) => {
    setActiveTab(id)
    setTabKey((k) => k + 1)
    if (!isDesktop) setSidebarOpen(false)
    requestAnimationFrame(() => {
      const heading = mainRef.current?.querySelector('h2')
      if (heading) {
        heading.setAttribute('tabindex', '-1')
        heading.focus({ preventScroll: true })
        mainRef.current?.scrollTo({ top: 0 })
      }
    })
  }, [isDesktop])

  if (coreError) return <ErrorState error={coreError} onRetry={coreReload} />

  const TabComponent = tabs[activeTab]
  const tab = getTab(activeTab)

  return (
    <div className="flex h-dvh flex-col">
      <TopBar
        summary={coreData.summary_stats}
        onToggleSidebar={toggleSidebar}
        sidebarOpen={sidebarOpen}
      />
      <div className="flex min-h-0 flex-1">
        {!isDesktop && sidebarOpen && (
          <div
            className="fixed inset-0 z-30 bg-nu-black/30 transition-opacity"
            onClick={() => setSidebarOpen(false)}
            aria-hidden="true"
          />
        )}
        <Sidebar
          activeTab={activeTab}
          onSelectTab={handleSelectTab}
          filters={filters}
          departmentNames={departmentNames}
          open={sidebarOpen}
          isOverlay={!isDesktop}
        />
        <main
          ref={mainRef}
          className="min-w-0 flex-1 overflow-y-auto px-4 py-5 md:px-6"
          role="main"
          aria-label={tab.label}
        >
          {coreLoading ? (
            <Skeleton height={400} label="Loading dashboard" />
          ) : (
            <Suspense fallback={<Skeleton height={400} label={`Loading ${tab.label}`} />}>
              <div key={tabKey} className="tab-enter">
                <TabComponent filters={filters} />
              </div>
            </Suspense>
          )}
          <Disclaimer />
        </main>
      </div>
    </div>
  )
}
