import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import PlotlyChart from '../components/charts/PlotlyChart'
import {
  CHROME, NODE, SUBSTITUTE, SEMANTIC,
} from '../styles/palette'
import { similarityColor } from '../styles/palette'
import {
  buildSimilarityMap,
  buildBottleneckSubstitutes,
  findRedundantClusters,
  extractProgramCourses,
  getVersionForTerms,
  resolveRanges,
  num,
  pct,
} from '../utils/dataTransforms'

export default function RedundancyAnalysis({ filters }) {
  const { data, loading, error, reload } = useData([
    'similarity_pairs.json',
    'courses.json',
    'bottleneck_scores.json',
    'programs.json',
  ])

  const [threshold, setThreshold] = useState(0.8)

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading redundancy analysis" />

  const { similarity_pairs: simData, courses, bottleneck_scores, programs } = data
  const scores = bottleneck_scores?.scores || {}
  const pairs = simData?.pairs || []

  return (
    <RedundancyInner
      pairs={pairs}
      courses={courses}
      scores={scores}
      programs={programs}
      filters={filters}
      threshold={threshold}
      setThreshold={setThreshold}
    />
  )
}

function RedundancyInner({ pairs, courses, scores, programs, filters, threshold, setThreshold }) {
  const visible = useMemo(() => {
    let nodes = new Set(Object.keys(courses))
    if (filters.program !== 'all') {
      const prog = programs.programs[filters.program]
      if (prog) {
        const version = getVersionForTerms(prog, filters.terms)
        const pc = extractProgramCourses(prog, 'all', version)
        const ranged = resolveRanges(prog, courses, version)
        nodes = new Set([...pc.keys(), ...ranged])
      }
    } else if (filters.department !== 'all') {
      nodes = new Set(
        Object.keys(courses).filter((c) => c.startsWith(filters.department + ' ')),
      )
    }
    return nodes
  }, [courses, programs, filters])

  const simMap = useMemo(
    () => buildSimilarityMap(pairs, threshold),
    [pairs, threshold],
  )

  const substitutes = useMemo(
    () => buildBottleneckSubstitutes(simMap, scores, visible, courses, { threshold }),
    [simMap, scores, visible, courses, threshold],
  )

  const clusters = useMemo(
    () => findRedundantClusters(simMap, visible, 0.85),
    [simMap, visible],
  )

  const bottleneckCount = [...visible].filter((c) => (scores[c] ?? 0) >= 0.5).length
  const substituteCount = [...substitutes.values()].reduce((n, subs) => n + subs.length, 0)

  return (
    <div>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
            Redundancy Analysis
          </h2>
          <div className="accent-bar" />
          <p className="mt-1 text-[0.8rem] text-muted">
            {bottleneckCount} bottleneck{bottleneckCount !== 1 ? 's' : ''} with{' '}
            {substituteCount} potential substitute{substituteCount !== 1 ? 's' : ''} at
            threshold {threshold.toFixed(2)}.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[0.75rem] font-bold text-nu-gray-700">
            Similarity threshold
          </label>
          <input
            type="range"
            min={0.6}
            max={0.95}
            step={0.05}
            value={threshold}
            onChange={(e) => setThreshold(parseFloat(e.target.value))}
            className="w-28 accent-nu-red"
          />
          <span className="w-8 text-[0.75rem] tabular-nums font-bold text-nu-gray-900">
            {threshold.toFixed(2)}
          </span>
        </div>
      </header>

      {substitutes.size === 0 ? (
        <Empty>
          No bottleneck-substitute pairs found at similarity {threshold.toFixed(2)}.
          Try lowering the threshold.
        </Empty>
      ) : (
        <>
          <SubstituteNetwork substitutes={substitutes} courses={courses} scores={scores} />

          <details className="mt-3" open>
            <summary className="cursor-pointer text-[0.75rem] font-bold text-nu-gray-700">
              How to Read This Graph
            </summary>
            <div className="mt-2 grid gap-4 rounded border border-nu-gray-200 bg-nu-white p-3 sm:grid-cols-3">
              <div>
                <p className="legend-title">Node Color</p>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: NODE.bottleneck }} />
                  Bottleneck courses blocking student progress
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: '#22c55e' }} />
                  Better alternatives (easier prerequisites)
                </div>
                <div className="legend-item">
                  <span className="legend-dot" style={{ backgroundColor: SUBSTITUTE.neutral }} />
                  Similar courses but not necessarily easier
                </div>
              </div>
              <div>
                <p className="legend-title">Graph Layout</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Left side: Bottleneck courses</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Right side: Alternative courses</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Connections show course similarity</p>
                <p className="legend-title mt-2">Line Color</p>
                <div className="legend-item">
                  <span className="legend-line" style={{ backgroundColor: '#dc2626' }} />
                  High similarity
                </div>
                <div className="legend-item">
                  <span className="legend-line" style={{ backgroundColor: '#94a3b8' }} />
                  Lower similarity
                </div>
              </div>
              <div>
                <p className="legend-title">Interaction</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Hover over nodes for course details</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Hover over lines for similarity scores</p>
                <p className="text-[0.72rem] text-nu-gray-700 py-0.5">Drag to pan, scroll to zoom</p>
              </div>
            </div>
          </details>

          <div className="mt-5 space-y-3">
            {[...substitutes.entries()].map(([bottleneck, subs]) => (
              <Card
                key={bottleneck}
                title={`${bottleneck} — ${courses[bottleneck]?.title || ''}`}
                subtitle={`RF score: ${num(scores[bottleneck], 3)} · ${subs.length} substitute${subs.length !== 1 ? 's' : ''}`}
              >
                <div className="space-y-2">
                  {subs.map((s) => (
                    <div
                      key={s.course}
                      className="flex items-start justify-between gap-3 border-b border-nu-gray-100 pb-2 last:border-0"
                    >
                      <div>
                        <span className="text-[0.8125rem] font-bold text-nu-gray-900">
                          {s.course}
                        </span>
                        <span className="ml-1.5 text-[0.8125rem] text-nu-gray-700">
                          {s.title}
                        </span>
                        {s.is_better_access && (
                          <span className="ml-1.5 badge-ok text-[0.6rem]">Better access</span>
                        )}
                        {s.is_mutual_bottleneck && (
                          <span className="ml-1.5 chip text-[0.6rem]">Mutual bottleneck</span>
                        )}
                      </div>
                      <span className="shrink-0 tabular-nums text-[0.8125rem] font-bold text-nu-gray-900">
                        {pct(s.similarity, 0)}
                      </span>
                    </div>
                  ))}
                </div>
              </Card>
            ))}
          </div>
        </>
      )}

      {clusters.length > 0 && (
        <div className="mt-6">
          <h3 className="section-heading">Redundant Course Clusters (at 0.85)</h3>
          <div className="space-y-3">
            {clusters.map((cluster, i) => (
              <Card key={i}>
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <span className="text-[0.8125rem] font-bold text-nu-gray-900">
                      {cluster.courses.join(', ')}
                    </span>
                    <span className="ml-2 text-[0.72rem] text-muted">
                      {cluster.same_dept ? 'Same department' : 'Cross-department'}
                    </span>
                  </div>
                  <span className="shrink-0 tabular-nums text-[0.8125rem] font-bold text-nu-gray-900">
                    Avg sim: {pct(cluster.avg_similarity, 0)}
                  </span>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function SubstituteNetwork({ substitutes, courses, scores }) {
  const { nodes, edgeTraces } = useMemo(() => {
    const bottlenecks = [...substitutes.keys()]
    const allSubs = new Set()
    const edges = []
    for (const [b, subs] of substitutes) {
      for (const s of subs) {
        allSubs.add(s.course)
        edges.push({ source: b, target: s.course, similarity: s.similarity, better: s.is_better_access })
      }
    }

    const bX = []
    const bY = []
    const bText = []
    const bHover = []
    bottlenecks.forEach((b, i) => {
      bX.push(0)
      bY.push(i)
      bText.push(b)
      const c = courses[b] || {}
      let h = `<b>BOTTLENECK: ${b}</b>`
      h += `<br>${c.title || ''}`
      h += `<br>Centrality: ${num(scores[b], 3)}`
      h += `<br>Unlocks: ${c.out_degree ?? 0} courses`
      h += `<br>Prerequisites: ${c.in_degree ?? 0}`
      h += `<br><br>Has ${(substitutes.get(b) || []).length} similar course(s)`
      bHover.push(h)
    })

    const allSubInfo = new Map()
    for (const subs of substitutes.values()) {
      for (const s of subs) {
        const existing = allSubInfo.get(s.course)
        if (!existing || s.is_better_access) allSubInfo.set(s.course, s)
      }
    }

    const subsArr = [...allSubs].sort()
    const sX = []
    const sY = []
    const sText = []
    const sHover = []
    const sColors = []
    subsArr.forEach((s, i) => {
      sX.push(300)
      sY.push(i * (bottlenecks.length / Math.max(subsArr.length, 1)))
      sText.push(s)
      const c = courses[s] || {}
      const subInfo = allSubInfo.get(s)
      let h = `<b>SUBSTITUTE: ${s}</b>`
      h += `<br>${c.title || ''}`
      if (subInfo) h += `<br>Similarity: ${num(subInfo.similarity, 2)}`
      h += `<br>Unlocks: ${c.out_degree ?? 0} courses`
      h += `<br>Prerequisites: ${c.in_degree ?? 0}`
      if (subInfo?.is_better_access) {
        h += '<br><br>✓ Easier access than bottleneck'
        sColors.push('#22c55e')
      } else {
        h += '<br><br>✗ Not easier than bottleneck'
        sColors.push(SUBSTITUTE.neutral)
      }
      sHover.push(h)
    })

    const bIdx = new Map(bottlenecks.map((b, i) => [b, i]))
    const sIdx = new Map(subsArr.map((s, i) => [s, i]))

    const edgeTraces = edges.map((e) => ({
      x: [0, 300],
      y: [bIdx.get(e.source), sIdx.get(e.target) * (bottlenecks.length / Math.max(subsArr.length, 1))],
      mode: 'lines',
      type: 'scatter',
      line: {
        color: similarityColor(e.similarity),
        width: 1 + e.similarity,
      },
      hoverinfo: 'text',
      text: `<b>${e.source} → ${e.target}</b><br>Similarity: ${e.similarity.toFixed(2)}<br>${e.better ? '✓ Better access' : '✗ Not easier'}<br>Substitute prereqs: ${courses[e.target]?.in_degree ?? '?'} vs ${courses[e.source]?.in_degree ?? '?'}`,
      showlegend: false,
    }))

    const nodes = [
      {
        x: bX, y: bY, text: bText, hovertext: bHover, hoverinfo: 'text',
        mode: 'markers+text', textposition: 'middle left', textfont: { size: 10 },
        type: 'scatter',
        marker: { color: NODE.bottleneck, size: 10, line: { width: 1, color: CHROME.white } },
        showlegend: false,
      },
      {
        x: sX, y: sY, text: sText, hovertext: sHover, hoverinfo: 'text',
        mode: 'markers+text', textposition: 'middle right', textfont: { size: 10 },
        type: 'scatter',
        marker: { color: sColors, size: 8, line: { width: 1, color: CHROME.white } },
        showlegend: false,
      },
    ]

    return { nodes, edgeTraces }
  }, [substitutes, courses, scores])

  return (
    <Card title="Bottleneck → Substitute Network">
      <div className="flex gap-4">
        <div className="min-w-0 flex-1">
          <PlotlyChart
            data={[...edgeTraces, ...nodes]}
            layout={{
              xaxis: { visible: false, range: [-80, 380] },
              yaxis: { visible: false, autorange: 'reversed' },
              showlegend: false,
              margin: { l: 8, r: 8, t: 8, b: 8 },
            }}
            height={Math.max(300, substitutes.size * 40)}
          />
        </div>
        <div className="shrink-0 w-40 rounded border border-nu-gray-200 bg-nu-white px-3 py-2 text-[0.7rem] self-start">
          <p className="font-bold uppercase tracking-wide text-nu-gray-700 mb-1.5">Legend</p>
          <div className="flex items-center gap-1.5 py-0.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: NODE.bottleneck }} />
            <span className="text-nu-gray-700">Bottleneck</span>
          </div>
          <div className="flex items-center gap-1.5 py-0.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: '#22c55e' }} />
            <span className="text-nu-gray-700">Better alternative</span>
          </div>
          <div className="flex items-center gap-1.5 py-0.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full shrink-0" style={{ backgroundColor: SUBSTITUTE.neutral }} />
            <span className="text-nu-gray-700">Similar (not easier)</span>
          </div>
          <div className="flex items-center gap-1.5 py-0.5 mt-1.5 border-t border-nu-gray-100 pt-1.5">
            <span className="inline-block h-0.5 w-4 rounded shrink-0" style={{ backgroundColor: '#dc2626' }} />
            <span className="text-nu-gray-700">High similarity</span>
          </div>
          <div className="flex items-center gap-1.5 py-0.5">
            <span className="inline-block h-0.5 w-4 rounded shrink-0" style={{ backgroundColor: '#94a3b8' }} />
            <span className="text-nu-gray-700">Lower similarity</span>
          </div>
        </div>
      </div>
    </Card>
  )
}
