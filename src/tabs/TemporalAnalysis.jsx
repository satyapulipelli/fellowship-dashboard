import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import { InfoTip } from '../components/shared/Tooltip'
import PlotlyChart from '../components/charts/PlotlyChart'
import { CHROME, SCALES } from '../styles/palette'
import { num, pct } from '../utils/dataTransforms'

const SUMMER_PREFIXES = ['Summer 1', 'Summer 2', 'Summer Full']

function isSummerLabel(label) {
  return SUMMER_PREFIXES.some((p) => label.startsWith(p))
}

export default function TemporalAnalysis() {
  const { data, loading, error, reload } = useData([
    'temporal_patterns.json',
    'department_metrics.json',
  ])

  const [metric, setMetric] = useState('enrollment')

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading temporal patterns" />

  return <TemporalInner temporal={data.temporal_patterns} metric={metric} setMetric={setMetric} />
}

function TemporalInner({ temporal, metric, setMetric }) {
  const filtered = useMemo(() => {
    const termLabels = temporal.term_labels || temporal.terms || []
    const keepIdx = termLabels
      .map((label, i) => ({ label, i }))
      .filter(({ label }) => !isSummerLabel(label))

    const filteredLabels = keepIdx.map(({ label }) => label)
    const filteredMatrices = {}
    for (const [key, matrix] of Object.entries(temporal.matrices || {})) {
      filteredMatrices[key] = matrix.map((row) =>
        keepIdx.map(({ i }) => row[i]),
      )
    }

    const filteredSeasons = {}
    if (temporal.seasons) {
      for (const [season, s] of Object.entries(temporal.seasons)) {
        if (!SUMMER_PREFIXES.includes(season)) filteredSeasons[season] = s
      }
    }

    const filteredLfl = (temporal.like_for_like || []).filter(
      (row) => !SUMMER_PREFIXES.includes(row.season),
    )

    return {
      termLabels: filteredLabels,
      matrices: filteredMatrices,
      seasons: filteredSeasons,
      like_for_like: filteredLfl,
    }
  }, [temporal])

  return (
    <div>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
            Temporal Analysis
          </h2>
          <div className="accent-bar" />
          <p className="mt-1 text-[0.8rem] text-muted">
            Seasonal enrollment patterns and department-level trends across Fall and Spring terms.
          </p>
        </div>
        <select
          className="select w-auto"
          value={metric}
          onChange={(e) => setMetric(e.target.value)}
        >
          <option value="enrollment">Enrollment</option>
          <option value="fill_rate">Fill Rate</option>
          <option value="waitlist">Waitlist</option>
          <option value="sections">Sections</option>
        </select>
      </header>

      <Card title="Department x Term Heatmap">
        <Heatmap
          departments={temporal.departments || []}
          termLabels={filtered.termLabels}
          matrix={filtered.matrices[metric]}
          metric={metric}
        />
      </Card>

      {Object.keys(filtered.seasons).length > 0 && (
        <div className="mt-4">
          <Card title="Season Summary">
            <div className="overflow-x-auto">
              <table className="w-full text-[0.75rem]">
                <thead>
                  <tr className="border-b border-nu-gray-200 text-left text-[0.7rem] font-bold uppercase text-muted">
                    <th className="px-2 py-1.5">Season</th>
                    <th className="px-2 py-1.5 text-right">Sections</th>
                    <th className="px-2 py-1.5 text-right">Enrollment</th>
                    <th className="px-2 py-1.5 text-right">Avg Size</th>
                    <th className="px-2 py-1.5 text-right">Fill Rate</th>
                    <th className="px-2 py-1.5 text-right">At Capacity</th>
                    <th className="px-2 py-1.5 text-right">Waitlist</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(filtered.seasons).map(([season, s]) => (
                    <tr key={season} className="border-b border-nu-gray-100 hover:bg-nu-gray-50">
                      <td className="px-2 py-1.5 font-bold">{season}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{s.sections?.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{s.total_enrollment?.toLocaleString()}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{num(s.mean_section_size, 1)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{pct(s.mean_fill_rate)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{pct(s.at_capacity_rate)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{pct(s.waitlist_rate)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}

      {filtered.like_for_like.length > 0 && (
        <div className="mt-4">
          <Card title="Like-for-Like Comparisons">
            <div className="overflow-x-auto">
              <table className="w-full text-[0.75rem]">
                <thead>
                  <tr className="border-b border-nu-gray-200 text-left text-[0.7rem] font-bold uppercase text-muted">
                    <th className="px-2 py-1.5">Season</th>
                    <th className="px-2 py-1.5">Term A</th>
                    <th className="px-2 py-1.5">Term B</th>
                    <th className="px-2 py-1.5 text-right">Enrollment A</th>
                    <th className="px-2 py-1.5 text-right">Enrollment B</th>
                    <th className="px-2 py-1.5 text-right">Change</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.like_for_like.map((row, i) => (
                    <tr key={i} className="border-b border-nu-gray-100 hover:bg-nu-gray-50">
                      <td className="px-2 py-1.5 font-bold">{row.season}</td>
                      <td className="px-2 py-1.5">{row.term_a_label}</td>
                      <td className="px-2 py-1.5">{row.term_b_label}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {row.enrollment_a?.toLocaleString()}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {row.enrollment_b?.toLocaleString()}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        <span className={row.pct_change > 0 ? 'text-ok font-bold' : row.pct_change < 0 ? 'text-bad font-bold' : ''}>
                          {row.pct_change > 0 ? '+' : ''}{num(row.pct_change, 1)}%
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </div>
  )
}

function Heatmap({ departments, termLabels, matrix, metric }) {
  if (!matrix || !matrix.length) return <Empty>No heatmap data for {metric}</Empty>

  return (
    <PlotlyChart
      data={[
        {
          z: matrix,
          x: termLabels,
          y: departments,
          type: 'heatmap',
          colorscale: SCALES.sequential,
          hovertemplate: '%{y} · %{x}: %{z:.1f}<extra></extra>',
        },
      ]}
      layout={{
        xaxis: { tickangle: -45, dtick: 1, title: { text: '' } },
        yaxis: { title: { text: '' } },
        margin: { l: 56, r: 16, t: 16, b: 64 },
      }}
      height={Math.max(280, departments.length * 40)}
    />
  )
}
