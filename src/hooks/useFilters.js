import { useCallback, useMemo, useRef, useState } from 'react'
import {
  programActiveInTerm,
  programAvailableTerms,
  getVersionForTerms,
  termDisplay,
} from '../utils/dataTransforms'

/**
 * The original's cascading sidebar filter chain, ported from
 * sidebar/filters/filters_server.py and server.py:get_graph.
 *
 * Rules, each traceable to the source:
 *
 *  1. Department XOR program. Committing one resets the other to "all"
 *     (server.py:78-86, via ui.update_select).
 *  2. Terms restrict the department list to departments offering something in those terms
 *     (_update_department_choices).
 *  3. Terms restrict the program list to programs with a version active in those terms
 *     (_update_program_choices, via program_active_in_term).
 *  4. A selected program restricts the term list to that program's active terms, across
 *     ALL versions rather than just the most recent (_get_program_available_terms).
 *  5. A selected department restricts the term list to terms it actually offers in
 *     (_update_term_choices).
 *  6. Selecting a program with no term chosen auto-selects its most recent term
 *     (_track_program_selection).
 *  7. If the selected program becomes inactive for the chosen terms, the program filter
 *     silently resets to "all" (server.py:92-98).
 *  8. The program dropdown is optgrouped Undergraduate / Graduate / Other, keyed off
 *     degree_type prefixes (cached_filtered_programs).
 *  9. Program codes that collide with a department code are excluded.
 *
 * The original also distinguished the *committed* selection from the raw selectize text so
 * typing did not trigger graph rebuilds. Native <select> has no such intermediate state,
 * so committed and current are the same thing here — the distinction is noted because it
 * explains why the original carried two reactive values per filter.
 */

const UNDERGRAD = new Set(['BS', 'BA', 'BFA', 'BARCH'])
const GRAD = new Set(['MA', 'MS', 'MBA', 'MPH', 'MFA', 'PHD'])

export function useFilters({ programs, courseTerms, departments }) {
  const [department, setDepartment] = useState('DS')
  const [program, setProgram] = useState('all')
  const [terms, setTerms] = useState([])
  const [concentration, setConcentration] = useState('all')
  const [notice, setNotice] = useState(null)

  // Rule 7 resets the program during derivation; a ref keeps that from looping.
  const healed = useRef(null)

  const allTerms = courseTerms?.terms || []
  const deptCodes = departments || []

  // ── Which departments offer something in which terms ──
  const deptTerms = useMemo(() => {
    if (!courseTerms) return new Map()
    const map = new Map()
    for (const [code, idxs] of Object.entries(courseTerms.offered)) {
      const dept = code.split(' ')[0]
      if (!map.has(dept)) map.set(dept, new Set())
      const set = map.get(dept)
      for (const i of idxs) set.add(courseTerms.terms[i])
    }
    return map
  }, [courseTerms])

  // ── Rule 8/9: program groups ──
  const programGroups = useMemo(() => {
    if (!programs) return { Undergraduate: [], Graduate: [], Other: [] }
    const groups = { Undergraduate: [], Graduate: [], Other: [] }
    for (const [code, p] of Object.entries(programs.programs)) {
      if (deptCodes.includes(code)) continue // rule 9
      const degree = (p.degree_type || '').toUpperCase()
      const bucket = UNDERGRAD.has(degree)
        ? 'Undergraduate'
        : GRAD.has(degree)
          ? 'Graduate'
          : 'Other'
      groups[bucket].push({ code, title: p.program_title })
    }
    for (const g of Object.keys(groups)) groups[g].sort((a, b) => a.title.localeCompare(b.title))
    return groups
  }, [programs, deptCodes])

  // ── Rule 2: available departments given selected terms ──
  const availableDepartments = useMemo(() => {
    if (!terms.length) return deptCodes
    return deptCodes.filter((d) => {
      const has = deptTerms.get(d)
      return has && terms.some((t) => has.has(t))
    })
  }, [terms, deptCodes, deptTerms])

  // ── Rule 3: available programs given selected terms ──
  const availableProgramGroups = useMemo(() => {
    if (!terms.length || !programs) return programGroups
    const out = {}
    for (const [group, items] of Object.entries(programGroups)) {
      out[group] = items.filter(({ code }) =>
        terms.some((t) => programActiveInTerm(programs.programs[code], t)),
      )
    }
    return out
  }, [terms, programGroups, programs])

  // ── Rules 4 and 5: available terms given program / department ──
  const availableTerms = useMemo(() => {
    let list = allTerms
    if (program !== 'all' && programs?.programs[program]) {
      list = programAvailableTerms(programs.programs[program], list)
    }
    if (department !== 'all') {
      const has = deptTerms.get(department)
      list = has ? list.filter((t) => has.has(t)) : []
    }
    return list
  }, [allTerms, program, department, programs, deptTerms])

  // ── Rule 7: self-heal a program that is inactive for the chosen terms ──
  const effectiveProgram = useMemo(() => {
    if (program === 'all' || !programs?.programs[program] || !terms.length) return program
    const active = terms.some((t) => programActiveInTerm(programs.programs[program], t))
    if (active) return program
    if (healed.current !== program) {
      healed.current = program
      setNotice(
        `${programs.programs[program].program_title} has no version active in the selected term(s) — program filter cleared.`,
      )
    }
    return 'all'
  }, [program, terms, programs])

  // ── Concentration options for the selected program, if any ──
  const concentrations = useMemo(() => {
    if (effectiveProgram === 'all' || !programs?.programs[effectiveProgram]) return []
    const version = getVersionForTerms(programs.programs[effectiveProgram], terms)
    return Object.entries(version.concentrations || {}).map(([code, c]) => ({
      code,
      title: c.title || c.name || code,
    }))
  }, [effectiveProgram, terms, programs])

  // ── The program version in force, for the sidebar's "Active Version" line ──
  const activeVersion = useMemo(() => {
    if (effectiveProgram === 'all' || !programs?.programs[effectiveProgram]) return null
    return getVersionForTerms(programs.programs[effectiveProgram], terms)
  }, [effectiveProgram, terms, programs])

  // ── Rule 1: mutually exclusive commits ──
  const selectDepartment = useCallback(
    (value) => {
      setDepartment(value)
      if (value !== 'all') {
        setProgram('all')
        setConcentration('all')
      }
      setNotice(null)
      healed.current = null
    },
    [],
  )

  const selectProgram = useCallback(
    (value) => {
      setProgram(value)
      setConcentration('all')
      if (value !== 'all') setDepartment('all')
      setNotice(null)
      healed.current = null

      // Rule 6: auto-select the most recent term when none is chosen
      if (value !== 'all' && terms.length === 0 && programs?.programs[value]) {
        const avail = programAvailableTerms(programs.programs[value], allTerms)
        if (avail.length) setTerms([avail[avail.length - 1]])
      }
    },
    [terms, programs, allTerms],
  )

  const toggleTerm = useCallback((code) => {
    setTerms((prev) =>
      prev.includes(code) ? prev.filter((t) => t !== code) : [...prev, code].sort(),
    )
    setNotice(null)
  }, [])

  const setAllTerms = useCallback((list) => {
    setTerms([...list].sort())
    setNotice(null)
  }, [])

  const reset = useCallback(() => {
    setDepartment('all')
    setProgram('all')
    setTerms([])
    setConcentration('all')
    setNotice(null)
    healed.current = null
  }, [])

  const isFiltered = department !== 'all' || effectiveProgram !== 'all' || terms.length > 0

  return {
    // state
    department,
    program: effectiveProgram,
    terms,
    concentration,
    notice,
    isFiltered,
    // options
    availableDepartments,
    availableProgramGroups,
    availableTerms,
    concentrations,
    activeVersion,
    // actions
    selectDepartment,
    selectProgram,
    setConcentration,
    toggleTerm,
    setAllTerms,
    reset,
    dismissNotice: () => setNotice(null),
    // helpers
    termLabel: termDisplay,
  }
}
