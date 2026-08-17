import FilterBar from '../shared/FilterBar'
import { TABS, TAB_GROUPS } from '../../tabs/registry'
import { prefetch } from '../../hooks/useData'

export default function Sidebar({ activeTab, onSelectTab, filters, departmentNames, open, isOverlay }) {
  const active = TABS.find((t) => t.id === activeTab)

  return (
    <aside
      className={`${
        isOverlay
          ? `fixed inset-y-0 left-0 z-40 w-sidebar shadow-xl transition-transform duration-200 ${
              open ? 'translate-x-0' : '-translate-x-full'
            }`
          : `${open ? 'w-sidebar' : 'w-0'} shrink-0 overflow-hidden transition-[width] duration-200`
      } border-r border-nu-gray-200 bg-nu-white`}
    >
      <div className="flex h-full w-sidebar flex-col">
        <nav className="border-b border-nu-gray-200 px-3 py-3" aria-label="Dashboard sections">
          {TAB_GROUPS.map((group) => (
            <div key={group} className="mb-3 last:mb-0">
              <p className="mb-1 px-1 text-[0.65rem] font-black uppercase tracking-wider text-muted">
                {group}
              </p>
              <ul>
                {TABS.filter((t) => t.group === group).map((tab) => {
                  const isActive = tab.id === activeTab
                  return (
                    <li key={tab.id}>
                      <button
                        type="button"
                        onClick={() => onSelectTab(tab.id)}
                        onMouseEnter={() => prefetch(tab.files)}
                        onFocus={() => prefetch(tab.files)}
                        aria-current={isActive ? 'page' : undefined}
                        className={`group flex w-full items-start gap-2 rounded px-2 py-1.5 text-left transition ${
                          isActive
                            ? 'bg-nu-red/8 text-nu-gray-900'
                            : 'text-nu-gray-700 hover:bg-nu-gray-50'
                        }`}
                      >
                        <span
                          className={`mt-[3px] h-3.5 w-[3px] shrink-0 rounded-full ${
                            isActive ? 'bg-nu-red' : 'bg-transparent'
                          }`}
                          aria-hidden="true"
                        />
                        <span className="min-w-0">
                          <span
                            className={`block truncate text-[0.8125rem] ${
                              isActive ? 'font-black' : 'font-bold'
                            }`}
                          >
                            {tab.label}
                          </span>
                          {isActive && (
                            <span className="mt-0.5 block text-[0.68rem] leading-snug text-muted">
                              {tab.blurb}
                            </span>
                          )}
                        </span>
                      </button>
                    </li>
                  )
                })}
              </ul>
            </div>
          ))}
        </nav>

        <div className="min-h-0 flex-1 overflow-y-auto">
          {active?.usesFilters ? (
            <FilterBar filters={filters} departmentNames={departmentNames} />
          ) : (
            <p className="px-4 py-4 text-[0.7rem] leading-snug text-muted">
              This view reports across the whole institution and is not affected by the
              department, program or term filters.
            </p>
          )}
        </div>

        <footer className="border-t border-nu-gray-200 px-4 py-3">
          <p className="text-[0.65rem] leading-snug text-muted">
            Rebuild of a Python Shiny dashboard built during a fellowship with a university
            registrar&apos;s office. All figures synthetic.
          </p>
        </footer>
      </div>
    </aside>
  )
}
