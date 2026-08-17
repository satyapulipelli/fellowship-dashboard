/**
 * Ports of the original Shiny dashboard's data logic.
 *
 * Anything here that has an original equivalent names it, so behaviour can be checked
 * against the source rather than guessed at.
 */

// ─────────────────────────────────────────────────────────────
// Terms — utils/term_utils.py
// ─────────────────────────────────────────────────────────────

/** Season sub-codes, from utils/program_utils._TERM_CODE_SEASON. */
export const SEASON_BY_CODE = {
  10: 'Fall',
  20: 'Spring',
  30: 'Summer 1',
  40: 'Summer 2',
  50: 'Summer Full',
}

export const SUMMER_SEASONS = ['Summer 1', 'Summer 2', 'Summer Full']

/** '202310' -> { academicYear: 2023, season: 'Fall', year: 2022, display: 'Fall 2022' } */
export function parseTermCode(code) {
  const ay = parseInt(String(code).slice(0, 4), 10)
  const season = SEASON_BY_CODE[String(code).slice(4)]
  // Fall belongs to the prior calendar year under academic-year coding
  const year = season === 'Fall' ? ay - 1 : ay
  return { academicYear: ay, season, year, display: `${season} ${year}` }
}

export function termDisplay(code) {
  return parseTermCode(code).display
}

export function isSummer(code) {
  return SUMMER_SEASONS.includes(parseTermCode(code).season)
}

/** utils/term_utils.semester_index — sub < 20 Fall, < 40 Spring, else Summer-as-Spring. */
export function semesterIndex(code) {
  const n = typeof code === 'number' ? code : parseInt(code, 10)
  const year = Math.floor(n / 100)
  const sub = n % 100
  return sub < 20 ? year * 2 : year * 2 + 1
}

/** utils/term_utils.term_delay — semesters between two terms, clamped at 0. */
export function termDelay(a, b) {
  return Math.max(0, semesterIndex(b) - semesterIndex(a))
}

// ─────────────────────────────────────────────────────────────
// Prerequisite groups — utils/course_utils.parse_prerequisite_groups
// ─────────────────────────────────────────────────────────────

/**
 * Returns AND-groups of OR-alternatives: a student must satisfy at least one course from
 * every group. Mirrors the original including its self-reference filtering.
 */
export function parsePrerequisiteGroups(course) {
  const logic = course.prereq_logic || 'NONE'
  let prereqs = course.prerequisites || []
  if (logic === 'NONE' || prereqs.length === 0) return []

  prereqs = prereqs.filter((p) => p !== course.course_code)
  if (prereqs.length === 0) return []

  if (logic === 'SINGLE' || logic === 'OR') return [new Set(prereqs)]
  if (logic === 'AND') return prereqs.map((p) => new Set([p]))

  if (logic === 'COMPLEX') {
    const valid = new Set(prereqs)
    const groups = []
    for (const part of (course.prerequisite_text || '').split(';')) {
      const codes = part
        .split(' or ')
        .map((s) => s.trim())
        .filter((s) => valid.has(s))
      if (codes.length) groups.push(new Set(codes))
    }
    const accounted = new Set(groups.flatMap((g) => [...g]))
    for (const p of prereqs) if (!accounted.has(p)) groups.push(new Set([p]))
    return groups.length ? groups : prereqs.map((p) => new Set([p]))
  }
  return []
}

// ─────────────────────────────────────────────────────────────
// Program course extraction — utils/program_utils.extract_program_courses
// ─────────────────────────────────────────────────────────────

const CHOICE_TYPES = new Set(['choice', 'credits', 'advisor'])
const SKIP_TYPES = new Set(['info', 'experiential'])

/**
 * @param {object} program a programs.json entry
 * @param {'required'|'all'} mode
 * @param {object} [version] defaults to the most recent
 * @returns {Map<string,string>} course code -> requirement type
 */
export function extractProgramCourses(program, mode = 'required', version) {
  const v = version || program.versions[program.versions.length - 1]
  const out = new Map()

  const add = (section, type) => {
    for (const c of section.courses || []) if (!out.has(c.code)) out.set(c.code, type)
    for (const o of section.options || []) {
      if (o.type === 'range' || !o.code) continue
      if (!out.has(o.code)) out.set(o.code, type)
    }
  }

  for (const sec of v.base_requirements?.sections || []) {
    const t = sec.type || ''
    if (SKIP_TYPES.has(t)) continue
    if (t === 'required') add(sec, 'core')
    else if (CHOICE_TYPES.has(t)) {
      if (mode === 'all') add(sec, 'elective')
    } else if (t === 'pathway' && (mode === 'all' || mode === 'pathways')) {
      add(sec, 'pathway')
    }
  }

  if (mode === 'all' || mode === 'concentrations') {
    for (const conc of Object.values(v.concentrations || {})) {
      for (const sec of conc.sections || []) add(sec, 'concentration')
    }
  }
  return out
}

/** graphs.py _resolve_range — expand an open range against the catalog. */
export function resolveRanges(program, courses, version) {
  const v = version || program.versions[program.versions.length - 1]
  const out = new Set()
  for (const sec of v.base_requirements?.sections || []) {
    for (const o of sec.options || []) {
      if (o.type !== 'range') continue
      const lo = parseInt(o.level_min || 0, 10)
      const hi = o.level_max ? parseInt(o.level_max, 10) : null
      for (const [code, c] of Object.entries(courses)) {
        if (c.department !== o.department) continue
        const n = parseInt(c.number, 10)
        if (n < lo || (hi !== null && n > hi)) continue
        out.add(code)
      }
    }
  }
  return out
}

// ─────────────────────────────────────────────────────────────
// Program versions — utils/program_utils.get_version_for_terms
// ─────────────────────────────────────────────────────────────

/** Parse the original's m/d/YYYY (or ISO) effective dates. */
function parseDate(s) {
  if (!s) return null
  const mdy = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec(s)
  if (mdy) return new Date(+mdy[3], +mdy[1] - 1, +mdy[2])
  const d = new Date(s)
  return isNaN(d) ? null : d
}

/** utils/program_utils._SEASON_MONTH_RANGES */
const SEASON_MONTHS = {
  Fall: [8, 12],
  Spring: [1, 5],
  'Summer 1': [6, 6],
  'Summer 2': [7, 7],
  'Summer Full': [6, 8],
}

/** utils/program_utils.version_overlaps_term */
export function versionOverlapsTerm(version, termCode) {
  const { season, year } = parseTermCode(termCode)
  const months = SEASON_MONTHS[season]
  if (!months) return false
  const termStart = new Date(year, months[0] - 1, 1)
  const termEnd = new Date(year, months[1] - 1, 28)
  const vs = parseDate(version.effective_period?.start_date)
  const ve = parseDate(version.effective_period?.end_date)
  if (!vs || !ve) return false
  return ve >= termStart && vs <= termEnd
}

/** utils/program_utils.program_active_in_term — any version overlapping. */
export function programActiveInTerm(program, termCode) {
  return (program.versions || []).some((v) => versionOverlapsTerm(v, termCode))
}

/**
 * utils/program_utils.get_version_for_terms — first version overlapping any selected
 * term, else the most recent by end_date.
 */
export function getVersionForTerms(program, terms = []) {
  for (const t of terms) {
    for (const v of program.versions) if (versionOverlapsTerm(v, t)) return v
  }
  let best = null
  let bestDate = null
  for (const v of program.versions) {
    const d = parseDate(v.effective_period?.end_date)
    if (d && (!bestDate || d > bestDate)) {
      bestDate = d
      best = v
    }
  }
  return best || program.versions[program.versions.length - 1]
}

/** All terms in which any version of a program is active. */
export function programAvailableTerms(program, allTerms) {
  return allTerms.filter((t) => programActiveInTerm(program, t))
}

// ─────────────────────────────────────────────────────────────
// Subgraph statistics
// ─────────────────────────────────────────────────────────────

/**
 * Recompute degree statistics over a filtered node set.
 *
 * courses.json ships whole-graph in_degree/out_degree, but the original's Graph
 * Statistics card reports on whatever is currently visible — under any filter the shipped
 * values are wrong for it. See DATA_CONTRACT "Degrees are whole-graph".
 *
 * @param {Set<string>} visible node codes currently rendered
 * @param {Array} edges prerequisites.json edges
 * @returns per-node degrees plus the card's aggregate rows
 */
export function subgraphStats(visible, edges, courses) {
  const inDeg = new Map()
  const outDeg = new Map()
  for (const code of visible) {
    inDeg.set(code, 0)
    outDeg.set(code, 0)
  }

  let prereqEdges = 0
  let coreqEdges = 0
  for (const e of edges) {
    if (!visible.has(e.source) || !visible.has(e.target)) continue
    if (e.type === 'prerequisite') {
      inDeg.set(e.target, inDeg.get(e.target) + 1)
      outDeg.set(e.source, outDeg.get(e.source) + 1)
      prereqEdges++
    } else {
      coreqEdges++
    }
  }

  const n = visible.size
  const inValues = [...inDeg.values()]
  const levelCounts = {}
  for (const code of visible) {
    const lvl = courses[code]?.level ?? 0
    levelCounts[lvl] = (levelCounts[lvl] || 0) + 1
  }

  // "Key Courses": top 5 by out-degree, zero excluded — graph_stats_server.py
  const keyCourses = [...outDeg.entries()]
      .filter(([, d]) => d > 0)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .slice(0, 5)
      .map(([code, degree]) => ({ code, degree }))

  return {
    inDeg,
    outDeg,
    totalCourses: n,
    totalDependencies: prereqEdges + coreqEdges,
    prerequisiteEdges: prereqEdges,
    corequisiteEdges: coreqEdges,
    avgPrereqs: n ? inValues.reduce((a, b) => a + b, 0) / n : 0,
    maxPrereqs: inValues.length ? Math.max(...inValues) : 0,
    keyCourses,
    levelCounts,
  }
}

/**
 * graphs.py compute_grey_nodes — BFS forward from removed courses over prerequisite
 * successors *and* corequisite out-edges, so the full affected chain greys out.
 */
export function computeGreyNodes(removed, edges) {
  const succ = new Map()
  for (const e of edges) {
    if (!succ.has(e.source)) succ.set(e.source, [])
    succ.get(e.source).push(e.target)
  }
  const grey = new Set(removed)
  const queue = [...removed]
  while (queue.length) {
    const node = queue.shift()
    for (const next of succ.get(node) || []) {
      if (!grey.has(next)) {
        grey.add(next)
        queue.push(next)
      }
    }
  }
  return grey
}

// ─────────────────────────────────────────────────────────────
// Similarity re-filtering — the threshold slider is live
// ─────────────────────────────────────────────────────────────

/**
 * Build a bidirectional similarity map at a threshold, from the compact pair tuples.
 * Mirrors load_data/load_similarity_data.load_similarity_data.
 *
 * @param {Array<[string,string,number]>} pairs
 */
export function buildSimilarityMap(pairs, threshold) {
  const map = new Map()
  for (const [a, b, score] of pairs) {
    if (score < threshold) continue // pairs ship sorted desc, but be explicit
    if (!map.has(a)) map.set(a, new Map())
    if (!map.has(b)) map.set(b, new Map())
    map.get(a).set(b, score)
    map.get(b).set(a, score)
  }
  return map
}

/**
 * analysis/redundancy_analysis.identify_bottleneck_substitutes, including the
 * mutual-bottleneck deduplication (higher score wins, ties by lexical order).
 */
export function buildBottleneckSubstitutes(simMap, scores, visible, courses, {
  threshold = 0.8,
  bottleneckThreshold = 0.5,
} = {}) {
  const inScope = [...visible].filter((c) => scores[c] !== undefined)
  const sorted = inScope.sort((a, b) => scores[b] - scores[a])
  const bottlenecks = new Set(sorted.filter((c) => scores[c] >= bottleneckThreshold))

  const out = new Map()
  const seenPairs = new Set()

  for (const course of sorted) {
    if (!bottlenecks.has(course) || scores[course] === 0) continue
    const similars = simMap.get(course)
    if (!similars) continue

    const subs = []
    const bLvl = courses[course]?.level ?? 0
    for (const [sim, score] of similars) {
      if (score < threshold || !visible.has(sim)) continue
      const sLvl = courses[sim]?.level ?? 0
      if (sLvl < bLvl) continue
      const subScore = scores[sim] ?? 0
      const isMutual = bottlenecks.has(sim)
      const pair = [course, sim].sort().join('|')
      if (isMutual) {
        if (seenPairs.has(pair)) continue
        seenPairs.add(pair)
        if (subScore > scores[course]) continue
        if (subScore === scores[course] && sim < course) continue
      }
      const bUn = courses[course]?.out_degree ?? 0
      const sUn = courses[sim]?.out_degree ?? 0
      const bPr = courses[course]?.in_degree ?? 0
      const sPr = courses[sim]?.in_degree ?? 0
      subs.push({
        course: sim,
        title: courses[sim]?.title || '',
        similarity: score,
        same_dept: courses[sim]?.department === courses[course]?.department,
        bottleneck_centrality: scores[course],
        substitute_centrality: subScore,
        bottleneck_unlocks: bUn,
        substitute_unlocks: sUn,
        bottleneck_prereqs: bPr,
        substitute_prereqs: sPr,
        is_better_access: sPr <= bPr,
        is_mutual_bottleneck: isMutual,
      })
    }
    if (subs.length) {
      subs.sort((a, b) => b.similarity - a.similarity)
      out.set(course, subs)
    }
  }
  return out
}

/**
 * analysis/redundancy_analysis.find_redundant_course_clusters — DFS over similarity edges
 * at a fixed 0.85 in the original, independent of the slider.
 */
export function findRedundantClusters(simMap, visible, threshold = 0.85) {
  const visited = new Set()
  const clusters = []

  for (const course of [...visible].sort()) {
    if (visited.has(course) || !simMap.has(course)) continue
    const cluster = new Set([course])
    const stack = [course]
    while (stack.length) {
      const current = stack.pop()
      visited.add(current)
      for (const [sim, score] of simMap.get(current) || []) {
        if (score >= threshold && visible.has(sim) && !visited.has(sim)) {
          cluster.add(sim)
          stack.push(sim)
        }
      }
    }
    if (cluster.size > 1) {
      const members = [...cluster].sort()
      const sims = []
      for (const a of members)
        for (const b of members)
          if (a < b && simMap.get(a)?.has(b)) sims.push(simMap.get(a).get(b))
      const depts = new Set(members.map((c) => c.split(' ')[0]))
      clusters.push({
        courses: members,
        size: members.length,
        avg_similarity: sims.length ? sims.reduce((a, b) => a + b, 0) / sims.length : 0,
        same_dept: depts.size === 1,
      })
    }
  }
  return clusters.sort((a, b) => b.avg_similarity - a.avg_similarity)
}

// ─────────────────────────────────────────────────────────────
// Bottleneck flags — bottleneck_pipeline.is_bottleneck (exact strings)
// ─────────────────────────────────────────────────────────────

export function bottleneckFlags(code, enrollment = {}, programCount = 0, scores = {}) {
  const flags = []
  if ((scores[code] ?? 0) >= 0.5) flags.push('High bottleneck risk')
  if (programCount >= 2) flags.push('High program demand')
  if ((enrollment.sections_per_semester ?? 0) < 2) flags.push('Low section availability')
  if ((enrollment.waitlist_frequency ?? 0) > 0.2) flags.push('High waitlist frequency')
  return flags
}

// ─────────────────────────────────────────────────────────────
// Formatting
// ─────────────────────────────────────────────────────────────

export const pct = (v, dp = 1) =>
  v === null || v === undefined || Number.isNaN(v) ? 'N/A' : `${(v * 100).toFixed(dp)}%`

export const num = (v, dp = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? 'N/A' : Number(v).toFixed(dp)

export const int = (v) =>
  v === null || v === undefined || Number.isNaN(v) ? 'N/A' : Math.round(v).toLocaleString()

/** utils/course_utils.parse_instructors — CourseLeaf instructor strings. */
export function parseInstructors(str) {
  if (!str || str === 'TBD') return ['TBD']
  return str
    .split(';')
    .map((part) => {
      const m = /^(.*?)\s*\(\d+\)\s*(?:\[(.*?)\])?/.exec(part.trim())
      if (!m) return null
      const role = m[2] ? m[2].split(',')[0].trim() : null
      return role ? `${m[1].trim()} (${role})` : m[1].trim()
    })
    .filter(Boolean)
}

// ─────────────────────────────────────────────────────────────
// CSV export
// ─────────────────────────────────────────────────────────────

export function toCSV(rows, columns) {
  if (!rows.length) return ''
  const cols = columns || Object.keys(rows[0])
  const esc = (v) => {
    const s = v === null || v === undefined ? '' : String(v)
    return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  return [cols.join(','), ...rows.map((r) => cols.map((c) => esc(r[c])).join(','))].join('\n')
}

export function downloadCSV(filename, rows, columns) {
  const blob = new Blob([toCSV(rows, columns)], { type: 'text/csv;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}
