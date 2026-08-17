import { useState } from 'react'

/**
 * Sidebar filter controls. Mirrors sidebar/filters/filters_ui.py: department, program,
 * a concentration selector that appears only when the program has concentrations, and a
 * multi-term selector. Help text is carried over from the original's ui.help_text.
 */
export default function FilterBar({ filters, departmentNames = {} }) {
  const {
    department,
    program,
    terms,
    concentration,
    notice,
    isFiltered,
    availableDepartments,
    availableProgramGroups,
    availableTerms,
    concentrations,
    activeVersion,
    selectDepartment,
    selectProgram,
    setConcentration,
    toggleTerm,
    setAllTerms,
    reset,
    dismissNotice,
    termLabel,
  } = filters

  const [termsOpen, setTermsOpen] = useState(false)
  const programCount = Object.values(availableProgramGroups).reduce(
    (n, g) => n + g.length,
    0,
  )

  return (
    <div className="space-y-4 px-4 py-4">
      {notice && (
        <div className="rounded border border-nu-gold bg-nu-gold/15 p-2 text-[0.7rem] leading-snug text-nu-gray-900">
          {notice}
          <button
            type="button"
            onClick={dismissNotice}
            className="mt-1 block font-bold underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* ── Department ── */}
      <div>
        <label className="field-label" htmlFor="f-department">
          Filter by Department
        </label>
        <select
          id="f-department"
          className="select"
          value={department}
          onChange={(e) => selectDepartment(e.target.value)}
        >
          <option value="all">All Departments</option>
          {availableDepartments.map((d) => (
            <option key={d} value={d}>
              {departmentNames[d] ? `${d} — ${departmentNames[d]}` : d}
            </option>
          ))}
        </select>
        <span className="field-help">
          Choose a department to filter courses offered only by that department.
        </span>
      </div>

      {/* ── Program ── */}
      <div>
        <label className="field-label" htmlFor="f-program">
          Filter by Program
        </label>
        <select
          id="f-program"
          className="select"
          value={program}
          onChange={(e) => selectProgram(e.target.value)}
        >
          <option value="all">All Programs ({programCount})</option>
          {Object.entries(availableProgramGroups).map(([group, items]) =>
            items.length ? (
              <optgroup key={group} label={group}>
                {items.map((p) => (
                  <option key={p.code} value={p.code}>
                    {p.title}
                  </option>
                ))}
              </optgroup>
            ) : null,
          )}
        </select>
        <span className="field-help">
          Choose a program to filter courses relevant to that program.
        </span>
        {activeVersion && (
          <p className="mt-1.5 text-[0.7rem] text-nu-gray-700">
            <span className="font-bold">Active version: </span>
            <span className="text-muted">
              {activeVersion.effective_period.start_date} to{' '}
              {activeVersion.effective_period.end_date}
            </span>
          </p>
        )}
      </div>

      {/* ── Concentration — only when the program has any ── */}
      {concentrations.length > 0 && (
        <div>
          <label className="field-label" htmlFor="f-concentration">
            Filter by Concentration
          </label>
          <select
            id="f-concentration"
            className="select"
            value={concentration}
            onChange={(e) => setConcentration(e.target.value)}
          >
            <option value="all">All Courses (Base + Options)</option>
            {concentrations.map((c) => (
              <option key={c.code} value={`CONC:${c.code}`}>
                Concentration: {c.title}
              </option>
            ))}
          </select>
          <span className="field-help">
            Show only the courses belonging to a specific concentration or pathway.
          </span>
        </div>
      )}

      {/* ── Terms ── */}
      <div>
        <div className="mb-1 flex items-baseline justify-between">
          <span className="field-label mb-0">Filter by Term</span>
          {terms.length > 0 && (
            <button
              type="button"
              onClick={() => setAllTerms([])}
              className="text-[0.7rem] font-bold text-nu-red hover:underline"
            >
              Clear
            </button>
          )}
        </div>

        <button
          type="button"
          onClick={() => setTermsOpen((v) => !v)}
          aria-expanded={termsOpen}
          className="select flex items-center justify-between text-left"
        >
          <span className={terms.length ? 'text-nu-gray-900' : 'text-muted'}>
            {terms.length === 0
              ? 'All terms (no filter)'
              : terms.length === 1
                ? termLabel(terms[0])
                : `${terms.length} terms selected`}
          </span>
          <svg
            width="12"
            height="12"
            viewBox="0 0 20 20"
            fill="currentColor"
            className={`shrink-0 text-muted transition ${termsOpen ? 'rotate-180' : ''}`}
            aria-hidden="true"
          >
            <path d="M5 7l5 6 5-6z" />
          </svg>
        </button>

        {terms.length > 0 && !termsOpen && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {terms.map((t) => (
              <button
                key={t}
                type="button"
                onClick={() => toggleTerm(t)}
                className="chip hover:bg-nu-gray-200"
                title="Remove this term"
              >
                {termLabel(t)}
                <span aria-hidden="true">×</span>
              </button>
            ))}
          </div>
        )}

        {termsOpen && (
          <div className="mt-1.5 max-h-56 overflow-y-auto rounded border border-nu-gray-200 bg-nu-white">
            {availableTerms.length === 0 ? (
              <p className="p-2 text-[0.7rem] text-muted">
                No terms available for the current selection.
              </p>
            ) : (
              availableTerms.map((t) => (
                <label
                  key={t}
                  className="flex cursor-pointer items-center gap-2 border-b border-nu-gray-100 px-2 py-1.5 text-[0.75rem] last:border-0 hover:bg-nu-gray-50"
                >
                  <input
                    type="checkbox"
                    checked={terms.includes(t)}
                    onChange={() => toggleTerm(t)}
                    className="accent-nu-red"
                  />
                  <span className="text-nu-gray-900">{termLabel(t)}</span>
                </label>
              ))
            )}
          </div>
        )}
        <span className="field-help">
          Select one or more terms to show only courses offered during those periods.
        </span>
      </div>

      {isFiltered && (
        <button type="button" onClick={reset} className="btn w-full justify-center">
          Reset all filters
        </button>
      )}
    </div>
  )
}
