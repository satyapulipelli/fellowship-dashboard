import { useCallback, useMemo, useRef, useEffect, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, FilterNudge } from '../components/shared/States'
import { InfoTip } from '../components/shared/Tooltip'
import PlotlyChart from '../components/charts/PlotlyChart'
import {
  CHROME, EDGE, NODE, LEVEL_COLORS, programColor, SURFACE,
} from '../styles/palette'

import {
  extractProgramCourses,
  resolveRanges,
  getVersionForTerms,
  subgraphStats,
  computeGreyNodes,
  int,
} from '../utils/dataTransforms'

const BOTTLENECK_THRESHOLD = 0.5
const ZOOM_LABEL_RATIO = 1.5
const Y_SPACING = 100

function computeSubgraphLayout(visibleSet, courses, edges, mode = 'alphabetical') {
  const levels = new Map()
  for (const code of visibleSet) {
    const lvl = courses[code]?.level ?? 0
    if (!levels.has(lvl)) levels.set(lvl, [])
    levels.get(lvl).push(code)
  }

  const sortedLevels = [...levels.keys()].sort((a, b) => b - a)

  if (mode === 'tree') {
    const parents = new Map()
    for (const e of edges) {
      if (!visibleSet.has(e.source) || !visibleSet.has(e.target)) continue
      if (!parents.has(e.target)) parents.set(e.target, [])
      parents.get(e.target).push(e.source)
    }
    const first = levels.get(sortedLevels[0])
    if (first) first.sort()
    const tempX = new Map()
    if (first) {
      for (let i = 0; i < first.length; i++) tempX.set(first[i], i)
    }
    for (let li = 1; li < sortedLevels.length; li++) {
      const nodes = levels.get(sortedLevels[li])
      nodes.sort((a, b) => {
        const pa = parents.get(a) || []
        const pb = parents.get(b) || []
        const avgA = pa.length ? pa.reduce((s, p) => s + (tempX.get(p) || 0), 0) / pa.length : Infinity
        const avgB = pb.length ? pb.reduce((s, p) => s + (tempX.get(p) || 0), 0) / pb.length : Infinity
        if (avgA !== avgB) return avgA - avgB
        return a.localeCompare(b)
      })
      for (let i = 0; i < nodes.length; i++) tempX.set(nodes[i], i)
    }
  } else {
    for (const arr of levels.values()) arr.sort()
  }

  const widest = Math.max(1, ...[...levels.values()].map((a) => a.length))
  const xSpacing = Math.max(40, Math.min(150, 12000 / widest))

  const pos = new Map()
  for (let li = 0; li < sortedLevels.length; li++) {
    const nodes = levels.get(sortedLevels[li])
    const n = nodes.length
    const startX = -(n - 1) * xSpacing / 2
    for (let i = 0; i < n; i++) {
      pos.set(nodes[i], { x: startX + i * xSpacing, y: li * Y_SPACING })
    }
  }
  return { pos, widest }
}

export default function GraphView({ filters }) {
  const { data, loading, error, reload } = useData([
    'courses.json',
    'prerequisites.json',
    'programs.json',
    'bottleneck_scores.json',
    'terms.json',
  ])

  const [layout, setLayout] = useState('layered')
  const [removedCourses, setRemovedCourses] = useState([])
  const [highlightShared, setHighlightShared] = useState(false)
  const [highlightBottlenecks, setHighlightBottlenecks] = useState(false)

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={600} label="Loading graph" />

  const { courses, prerequisites, programs, bottleneck_scores, terms } = data
  const scores = bottleneck_scores?.scores || {}
  const edges = prerequisites?.edges || []

  return (
    <GraphViewInner
      courses={courses}
      edges={edges}
      programs={programs}
      scores={scores}
      filters={filters}
      layout={layout}
      setLayout={setLayout}
      removedCourses={removedCourses}
      setRemovedCourses={setRemovedCourses}
      highlightShared={highlightShared}
      setHighlightShared={setHighlightShared}
      highlightBottlenecks={highlightBottlenecks}
      setHighlightBottlenecks={setHighlightBottlenecks}
    />
  )
}

function GraphViewInner({
  courses,
  edges,
  programs,
  scores,
  filters,
  layout,
  setLayout,
  removedCourses,
  setRemovedCourses,
  highlightShared,
  setHighlightShared,
  highlightBottlenecks,
  setHighlightBottlenecks,
}) {
  const visible = useMemo(() => {
    let nodes = new Set(Object.keys(courses))

    if (filters.program !== 'all') {
      const prog = programs.programs[filters.program]
      if (prog) {
        const version = getVersionForTerms(prog, filters.terms)
        const mode = 'all'
        const programCourses = extractProgramCourses(prog, mode, version)
        const ranged = resolveRanges(prog, courses, version)
        nodes = new Set([...programCourses.keys(), ...ranged])
      }
    } else if (filters.department !== 'all') {
      nodes = new Set(
        Object.keys(courses).filter((c) => c.startsWith(filters.department + ' ')),
      )
    }

    if (filters.terms.length > 0) {
      nodes = new Set(
        [...nodes].filter((c) => {
          const yrs = courses[c]?.catalog_years || []
          return yrs.length === 0 || filters.terms.some((t) => {
            const ay = parseInt(String(t).slice(0, 4), 10)
            return yrs.includes(ay)
          })
        }),
      )
    }

    return nodes
  }, [courses, programs, filters])

  const greyNodes = useMemo(
    () => computeGreyNodes(removedCourses, edges),
    [removedCourses, edges],
  )

  const stats = useMemo(
    () => subgraphStats(visible, edges, courses),
    [visible, edges, courses],
  )

  const subgraph = useMemo(
    () => computeSubgraphLayout(visible, courses, edges, layout === 'layered' ? 'alphabetical' : 'tree'),
    [visible, courses, edges, layout],
  )

  const [showLabels, setShowLabels] = useState(false)

  const { nodeTrace, edgeTraces, nNodes, nEdges, bounds } = useMemo(() => {
    const visibleArr = [...visible]
    const n = visibleArr.length
    const baseSize = Math.max(18, Math.min(40, 700 / Math.max(n, 1)))
    const edgeWidth = Math.max(1, Math.min(3, 50 / Math.max(n, 1)))

    const nodeX = []
    const nodeY = []
    const nodeColor = []
    const nodeSize = []
    const nodeText = []
    const hoverText = []

    for (const code of visibleArr) {
      const c = courses[code]
      const p = subgraph.pos.get(code) || { x: 0, y: 0 }
      nodeX.push(p.x)
      nodeY.push(p.y)

      const isRemoved = removedCourses.includes(code)
      const isGreyed = greyNodes.has(code) && !isRemoved
      const isBottleneck = (scores[code] ?? 0) >= BOTTLENECK_THRESHOLD
      const pCount = c.program_count || 0

      let color
      if (isRemoved) color = NODE.removed
      else if (isGreyed) color = NODE.greyed
      else if (highlightBottlenecks && isBottleneck) color = NODE.bottleneck
      else if (highlightBottlenecks) color = NODE.dimmed
      else if (highlightShared) color = programColor(pCount)
      else color = LEVEL_COLORS[c.level] || LEVEL_COLORS[0]

      nodeColor.push(color)
      nodeSize.push(highlightBottlenecks && isBottleneck ? baseSize * 1.3 : baseSize)
      nodeText.push(code)

      const prereqCount = stats.inDeg.get(code) ?? c.in_degree ?? 0
      const outDeg = stats.outDeg.get(code) ?? c.out_degree ?? 0

      let ht = `<b>${code}</b><br>${c.title}<br>Level ${c.level}00 · ${c.credits} cr`
      ht += `<br>Prerequisites: ${prereqCount}`
      if (c.corequisites?.length) ht += `<br>Corequisites: ${c.corequisites.join(', ')}`
      ht += `<br>Unlocks: ${outDeg} courses`

      const elective = c.elective_context
      if (elective) {
        ht += '<br>─────────────────────'
        if (elective.elective_type === 'range') {
          ht += '<br><b>Elective (Open Range)</b>'
          if (elective.section_name) ht += `<br>Section: ${elective.section_name}`
          if (elective.choice_label) ht += `<br>Range: ${elective.choice_label}`
        } else {
          if (elective.section_name) ht += `<br><b>${elective.section_name}</b>`
          if (elective.choice_label) ht += `<br>${elective.choice_label}`
        }
      }

      if (pCount > 0) {
        ht += `<br><br><b>Programs: ${pCount}</b>`
        const progs = c.programs || []
        for (const p of progs.slice(0, 5)) ht += `<br>  • ${p}`
        if (progs.length > 5) ht += `<br>  … and ${progs.length - 5} more`
      }

      if (isBottleneck) ht += '<br><b>Bottleneck</b>'
      if (isRemoved) ht += '<br><b>REMOVED (what-if)</b>'
      if (isGreyed) ht += '<br><i>Affected by removed course</i>'

      hoverText.push(ht)
    }

    const nodeTrace = {
      x: nodeX,
      y: nodeY,
      text: nodeText,
      customdata: visibleArr,
      hovertext: hoverText,
      hoverinfo: 'text',
      mode: 'markers',
      type: 'scatter',
      textposition: 'top center',
      textfont: { size: 11, color: '#1f2937', family: 'Impact, Arial Black, sans-serif', weight: 900 },
      marker: {
        color: nodeColor,
        size: nodeSize,
        opacity: 0.9,
        line: { width: 1.5, color: CHROME.white },
      },
    }

    const prereqX = []
    const prereqY = []
    const coreqX = []
    const coreqY = []
    let edgeCount = 0

    for (const e of edges) {
      if (!visible.has(e.source) || !visible.has(e.target)) continue
      edgeCount++

      const sp = subgraph.pos.get(e.source) || { x: 0, y: 0 }
      const tp = subgraph.pos.get(e.target) || { x: 0, y: 0 }
      const sx = sp.x, sy = sp.y, tx = tp.x, ty = tp.y

      if (e.type === 'corequisite') {
        coreqX.push(sx, tx, null)
        coreqY.push(sy, ty, null)
      } else {
        prereqX.push(sx, tx, null)
        prereqY.push(sy, ty, null)
      }
    }

    const edgeTraces = [
      {
        x: prereqX,
        y: prereqY,
        mode: 'lines',
        type: 'scatter',
        line: { color: EDGE.prerequisite.color, width: edgeWidth, dash: EDGE.prerequisite.dash },
        opacity: 0.6,
        hoverinfo: 'skip',
        showlegend: false,
      },
    ]
    if (coreqX.length) {
      edgeTraces.push({
        x: coreqX,
        y: coreqY,
        mode: 'lines',
        type: 'scatter',
        line: { color: EDGE.corequisite.color, width: edgeWidth + 0.5, dash: EDGE.corequisite.dash },
        opacity: 0.6,
        hoverinfo: 'skip',
        showlegend: false,
      })
    }

    const xMin = Math.min(...nodeX)
    const xMax = Math.max(...nodeX)
    const yMin = Math.min(...nodeY)
    const yMax = Math.max(...nodeY)
    const xPad = Math.max(80, (xMax - xMin) * 0.08)
    const yPad = Math.max(40, (yMax - yMin) * 0.08)
    const bounds = {
      xRange: [xMin - xPad, xMax + xPad],
      yRange: [yMin - yPad, yMax + yPad],
    }

    return { nodeTrace, edgeTraces, nNodes: n, nEdges: edgeCount, bounds }
  }, [visible, courses, edges, removedCourses, greyNodes, scores,
      highlightBottlenecks, highlightShared, stats, subgraph])

  const courseOptions = useMemo(
    () => [...visible].sort(),
    [visible],
  )

  const addRemoved = useCallback((code) => {
    if (code && !removedCourses.includes(code)) {
      setRemovedCourses([...removedCourses, code])
    }
  }, [removedCourses, setRemovedCourses])

  const restoreCourse = useCallback((code) => {
    setRemovedCourses(removedCourses.filter((c) => c !== code))
  }, [removedCourses, setRemovedCourses])

  const fullSpanRef = useRef(bounds.xRange[1] - bounds.xRange[0])
  const [layoutRevision, setLayoutRevision] = useState(0)

  useEffect(() => {
    fullSpanRef.current = bounds.xRange[1] - bounds.xRange[0]
    setShowLabels(false)
    setLayoutRevision((r) => r + 1)
  }, [bounds])

  const onRelayout = useCallback((event) => {
    let xr0, xr1
    if (event['xaxis.range']) {
      xr0 = event['xaxis.range'][0]; xr1 = event['xaxis.range'][1]
    } else if (event['xaxis.range[0]'] != null) {
      xr0 = event['xaxis.range[0]']; xr1 = event['xaxis.range[1]']
    }
    if (xr0 != null && xr1 != null) {
      const ratio = fullSpanRef.current / (xr1 - xr0)
      setShowLabels(ratio >= ZOOM_LABEL_RATIO)
      return
    }
    if (event['xaxis.autorange'] || event['yaxis.autorange']) {
      setShowLabels(false)
    }
  }, [])

  const plotData = useMemo(() => {
    const traces = [...edgeTraces]
    const nt = { ...nodeTrace, mode: showLabels ? 'markers+text' : 'markers' }
    traces.push(nt)
    return traces
  }, [edgeTraces, nodeTrace, showLabels])

  return (
    <div>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
            Graph View
          </h2>
          <div className="accent-bar" />
        </div>
        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-[0.75rem] text-nu-gray-700">
            <input
              type="checkbox"
              checked={highlightBottlenecks}
              onChange={(e) => setHighlightBottlenecks(e.target.checked)}
              className="accent-nu-red"
            />
            Bottlenecks
          </label>
          <label className="flex items-center gap-1.5 text-[0.75rem] text-nu-gray-700">
            <input
              type="checkbox"
              checked={highlightShared}
              onChange={(e) => setHighlightShared(e.target.checked)}
              className="accent-nu-red"
            />
            Cross-program
          </label>
          <select
            className="select w-auto"
            value={layout}
            onChange={(e) => setLayout(e.target.value)}
          >
            <option value="layered">Layered</option>
            <option value="hierarchical">Hierarchical</option>
          </select>
        </div>
      </header>

      {visible.size > 100 && filters.department === 'all' && filters.program === 'all' && (
        <FilterNudge count={visible.size} />
      )}

      <Card
        title={`Course Dependency Graph (${nNodes} courses, ${nEdges} connections)`}
      >
        <PlotlyChart
          data={plotData}
          layout={{
            xaxis: { visible: false, range: bounds.xRange },
            yaxis: { visible: false, range: bounds.yRange },
            showlegend: false,
            margin: { l: 0, r: 0, t: 8, b: 0 },
            dragmode: 'pan',
            paper_bgcolor: SURFACE.paperBg,
            uirevision: layoutRevision,
          }}
          config={{ scrollZoom: true, modeBarButtonsToRemove: ['lasso2d', 'select2d'] }}
          onRelayout={onRelayout}
          height={750}
          style={{ width: '100%', height: '750px' }}
        />
      </Card>

      <div className="mt-4">
        <Card title={<>What-If Simulation<InfoTip text="Remove a course to see which downstream courses would be affected. Grey nodes indicate courses that lose a prerequisite." /></>}>
          <div className="flex items-center gap-2">
            <select
              className="select flex-1"
              defaultValue=""
              onChange={(e) => { addRemoved(e.target.value); e.target.value = '' }}
            >
              <option value="" disabled>Select a course to remove…</option>
              {courseOptions
                .filter((c) => !removedCourses.includes(c))
                .map((c) => (
                  <option key={c} value={c}>{c} — {courses[c]?.title}</option>
                ))}
            </select>
            {removedCourses.length > 0 && (
              <button
                type="button"
                className="btn"
                onClick={() => setRemovedCourses([])}
              >
                Restore all
              </button>
            )}
          </div>
          {removedCourses.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {removedCourses.map((c) => (
                <button
                  key={c}
                  type="button"
                  className="chip bg-nu-gray-900 text-nu-white hover:bg-nu-gray-700"
                  onClick={() => restoreCourse(c)}
                  title="Click to restore"
                >
                  {c} ✕
                </button>
              ))}
              <span className="text-[0.7rem] text-muted self-center ml-1">
                {greyNodes.size} downstream course{greyNodes.size !== 1 ? 's' : ''} affected
              </span>
            </div>
          )}
        </Card>
      </div>

      <div className="mt-4 grid gap-4 lg:grid-cols-4">
        <Card title="Summary">
          <div className="stat-row">
            <span className="stat-label">
              Total Courses
              <InfoTip text="Total number of courses currently visible in the graph." />
            </span>
            <span className="stat-value">{int(stats.totalCourses)}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">
              Dependencies
              <InfoTip text="Total number of prerequisite relationships between the selected courses." />
            </span>
            <span className="stat-value">{int(stats.totalDependencies)}</span>
          </div>
        </Card>
        <Card title="Complexity">
          <div className="stat-row">
            <span className="stat-label">
              Avg Prerequisites
              <InfoTip text="Average number of prerequisites per course within the currently selected graph." />
            </span>
            <span className="stat-value">{stats.avgPrereqs.toFixed(2)}</span>
          </div>
          <div className="stat-row">
            <span className="stat-label">
              Max Prerequisites
              <InfoTip text="Maximum number of prerequisites required by any single course in the current graph." />
            </span>
            <span className="stat-value">{stats.maxPrereqs}</span>
          </div>
        </Card>
        <Card title={<>Key Courses<InfoTip text="Courses that unlock the largest number of other courses in the current graph." /></>}>
          {stats.keyCourses.length > 0 ? (
            <ul className="space-y-1 text-[0.8125rem]">
              {stats.keyCourses.map((k) => (
                <li key={k.code} className="flex justify-between gap-2">
                  <span className="truncate font-bold text-nu-gray-900">{k.code}</span>
                  <span className="shrink-0 tabular-nums text-muted">{k.degree} deps</span>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-[0.75rem] text-muted">No outgoing edges in view</p>
          )}
        </Card>
        <Card title={<>Level Distribution<InfoTip text="Distribution of courses grouped by academic level (e.g., 1000-level, 2000-level)." /></>}>
          {Object.entries(stats.levelCounts)
            .sort(([a], [b]) => a - b)
            .map(([lvl, count]) => (
              <div key={lvl} className="stat-row">
                <span className="stat-label flex items-center gap-1.5">
                  <span
                    className="inline-block h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: LEVEL_COLORS[lvl] || LEVEL_COLORS[0] }}
                  />
                  {lvl}000-level
                </span>
                <span className="stat-value">{count}</span>
              </div>
            ))}
        </Card>
      </div>

      <GraphLegend />
    </div>
  )
}


function GraphLegend() {
  return (
    <details className="mt-4" open>
      <summary className="cursor-pointer text-[0.75rem] font-bold text-nu-gray-700">
        Legend
      </summary>
      <div className="mt-2 grid gap-4 rounded border border-nu-gray-200 bg-nu-white p-3 sm:grid-cols-4">
        <div>
          <p className="legend-title">Connection Types</p>
          <div className="legend-item">
            <span className="legend-line" style={{ backgroundColor: EDGE.prerequisite.color }} />
            Prerequisites
          </div>
          <div className="legend-item">
            <span className="legend-line" style={{ backgroundColor: EDGE.corequisite.color, borderBottom: '2px dashed' }} />
            Corequisites
          </div>
        </div>
        <div>
          <p className="legend-title">Course Levels</p>
          {[1, 2, 3, 4, 5, 6].map((l) => (
            LEVEL_COLORS[l] && (
              <div key={l} className="legend-item">
                <span className="legend-dot" style={{ backgroundColor: LEVEL_COLORS[l] }} />
                {l}000-level
              </div>
            )
          ))}
        </div>
        <div>
          <p className="legend-title">Cross-Program View</p>
          <p className="legend-helper">When "Cross-program" is enabled</p>
          <div className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: '#3b82f6' }} />
            1 program
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: '#8b5cf6' }} />
            2 programs
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: '#ec4899' }} />
            3 programs
          </div>
          <div className="legend-item">
            <span className="legend-dot" style={{ backgroundColor: '#dc2626' }} />
            4+ programs
          </div>
        </div>
        <div>
          <p className="legend-title">Interaction</p>
          <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Hover over nodes for details</p>
          <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Drag to pan the graph</p>
          <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Use toolbar to zoom in/out</p>
        </div>
      </div>
    </details>
  )
}
