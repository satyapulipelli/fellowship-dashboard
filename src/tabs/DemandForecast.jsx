import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import { InfoTip, WithTooltip } from '../components/shared/Tooltip'
import PlotlyChart from '../components/charts/PlotlyChart'
import { CHROME, SEMANTIC } from '../styles/palette'
import { int, num, pct } from '../utils/dataTransforms'

export default function DemandForecast({ filters }) {
  const { data, loading, error, reload } = useData([
    'forecast_scenarios.json',
    'courses.json',
    'department_metrics.json',
  ])

  const [growthPct, setGrowthPct] = useState('0')

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading demand forecast" />

  const { forecast_scenarios: forecast, courses, department_metrics: depts } = data

  return (
    <DemandInner
      forecast={forecast}
      courses={courses}
      depts={depts}
      filters={filters}
      growthPct={growthPct}
      setGrowthPct={setGrowthPct}
    />
  )
}

function DemandInner({ forecast, courses, depts, filters, growthPct, setGrowthPct }) {
  const invariantMap = useMemo(() => {
    const map = new Map()
    for (const c of forecast.courses) map.set(c.course, c)
    return map
  }, [forecast.courses])

  const scenario = forecast.scenarios[growthPct] || {}
  const deltaKeys = forecast.delta_keys || ['weighted_demand', 'shortage', 'sections_needed', 'priority_score']

  const rows = useMemo(() => {
    const deltas = scenario.deltas || {}
    let list = []

    for (const [code, delta] of Object.entries(deltas)) {
      const inv = invariantMap.get(code) || {}
      const row = { code, ...inv }
      deltaKeys.forEach((k, i) => { row[k] = delta[i] })
      row.department = inv.department || code.split(' ')[0]
      row.title = inv.title || courses[code]?.title || ''
      row.capacity = inv.current_capacity ?? 0
      row.ml_risk = inv.ml_risk ?? 0
      list.push(row)
    }

    if (filters.department !== 'all') {
      list = list.filter((r) => r.department === filters.department)
    }

    list.sort((a, b) => (b.priority_score ?? 0) - (a.priority_score ?? 0))
    return list
  }, [scenario, invariantMap, deltaKeys, courses, filters])

  const kpis = scenario.kpis || {}
  const shortageCount = rows.filter((r) => (r.shortage ?? 0) > 0).length

  return (
    <div>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
            Demand Forecast
          </h2>
          <div className="accent-bar" />
          <p className="mt-1 text-[0.8rem] text-muted">
            Capacity shortfall projections for {forecast.forecast_term_label}.{' '}
            {shortageCount} course{shortageCount !== 1 ? 's' : ''} with projected shortages under +{growthPct}% growth.
          </p>
        </div>
        <select
          className="select w-auto"
          value={growthPct}
          onChange={(e) => setGrowthPct(e.target.value)}
        >
          {(forecast.growth_scenarios || []).map((g) => (
            <option key={g} value={String(g)}>
              {g === 0 ? 'Baseline (0%)' : `+${g}% Growth`}
            </option>
          ))}
        </select>
      </header>

      <div className="mb-5 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Plans submitted"
          tip="Total student enrollment plan submissions used to estimate demand. Each count represents one student planning one term."
          value={int(kpis.total_plans_submitted)}
        />
        <KpiCard
          label="Courses with shortages"
          tip="Number of courses where projected demand exceeds current capacity at the selected growth rate."
          value={int(kpis.courses_with_shortages)}
        />
        <KpiCard
          label="Total seat shortage"
          tip="Aggregate number of student seats that would be unfilled across all courses with demand exceeding capacity."
          value={int(Math.round(kpis.total_shortage ?? 0))}
        />
        <KpiCard
          label="Sections to add"
          tip="Estimated number of additional sections needed across all departments to meet projected demand."
          value={int(kpis.sections_needed)}
        />
      </div>

      <Card title="Demand vs Capacity — Top 20">
        <DemandCapacityChart rows={rows.slice(0, 20)} />
      </Card>

      {scenario.recommendations && scenario.recommendations.length > 0 && (
        <div className="mt-4">
          <Card title="Recommendations">
            <div className="space-y-2">
              {scenario.recommendations.slice(0, 10).map((r, i) => (
                <div key={i} className="border-b border-nu-gray-100 pb-2 last:border-0">
                  <div className="flex items-start justify-between gap-3">
                    <span className="text-[0.8125rem] font-bold text-nu-gray-900">
                      {r.course}
                    </span>
                    <span className={`chip text-[0.65rem] ${
                      r.urgency === 'HIGH' ? 'bg-bad/15 text-bad' :
                      r.urgency === 'MEDIUM' ? 'bg-warn/15 text-nu-gray-900' :
                      ''
                    }`}>
                      {r.urgency}
                    </span>
                  </div>
                  <p className="text-[0.75rem] text-nu-gray-700">{r.action}</p>
                  <p className="text-[0.7rem] text-muted">{r.reason}</p>
                </div>
              ))}
            </div>
          </Card>
        </div>
      )}

      <div className="mt-4">
        <Card title="Course Detail">
          {rows.length === 0 ? (
            <Empty>No courses match the current filters.</Empty>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[0.75rem]">
                <thead>
                  <tr className="border-b border-nu-gray-200 text-left text-[0.7rem] font-bold uppercase text-muted">
                    <th className="px-2 py-1.5">Course</th>
                    <th className="px-2 py-1.5">Title</th>
                    <th className="px-2 py-1.5 text-right">Demand</th>
                    <th className="px-2 py-1.5 text-right">Capacity</th>
                    <th className="px-2 py-1.5 text-right">Shortage</th>
                    <th className="px-2 py-1.5 text-right">Sections</th>
                    <th className="px-2 py-1.5 text-right">Priority</th>
                    <th className="px-2 py-1.5 text-right">Risk</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.slice(0, 100).map((r) => (
                    <tr key={r.code} className="border-b border-nu-gray-100 hover:bg-nu-gray-50">
                      <td className="px-2 py-1.5 font-bold">{r.code}</td>
                      <td className="max-w-[200px] truncate px-2 py-1.5">{r.title}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(r.weighted_demand, 0)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(r.capacity, 0)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {r.shortage > 0 ? (
                          <span className="font-bold text-bad">{num(r.shortage, 0)}</span>
                        ) : (
                          <span className="text-muted">—</span>
                        )}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(r.sections_needed, 0)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(r.priority_score, 1)}
                      </td>
                      <td className="px-2 py-1.5 text-right">
                        {r.ml_risk >= 0.5 ? (
                          <span className="badge-bad">{pct(r.ml_risk, 0)}</span>
                        ) : r.ml_risk >= 0.3 ? (
                          <span className="badge-warn">{pct(r.ml_risk, 0)}</span>
                        ) : (
                          <span className="text-muted">{pct(r.ml_risk, 0)}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {rows.length > 100 && (
                <p className="py-2 text-center text-[0.7rem] text-muted">
                  Showing 100 of {rows.length}. Use filters to narrow.
                </p>
              )}
            </div>
          )}
        </Card>
      </div>
    </div>
  )
}

function KpiCard({ label, value, tip }) {
  return (
    <div className="card px-4 py-3">
      <div className="text-[1.2rem] font-black leading-tight tabular-nums text-nu-gray-900">
        {value}
      </div>
      <div className="mt-0.5 text-[0.72rem] font-bold uppercase tracking-wide text-muted">
        {label}
        {tip && <InfoTip text={tip} />}
      </div>
    </div>
  )
}

function DemandCapacityChart({ rows }) {
  if (!rows.length) return <Empty>No data</Empty>
  return (
    <PlotlyChart
      data={[
        {
          x: rows.map((r) => r.code),
          y: rows.map((r) => r.weighted_demand ?? 0),
          name: 'Demand',
          type: 'bar',
          marker: { color: CHROME.blue, opacity: 0.85 },
          hovertemplate: '%{x}: %{y:.0f}<extra>Demand</extra>',
        },
        {
          x: rows.map((r) => r.code),
          y: rows.map((r) => r.capacity ?? 0),
          name: 'Capacity',
          type: 'bar',
          marker: { color: CHROME.gray200 },
          hovertemplate: '%{x}: %{y:.0f}<extra>Capacity</extra>',
        },
      ]}
      layout={{
        barmode: 'group',
        xaxis: { tickangle: -45 },
        yaxis: { title: { text: 'Students' } },
        margin: { l: 48, r: 16, t: 16, b: 80 },
        legend: { orientation: 'h', x: 0, y: 1.08 },
      }}
      height={360}
    />
  )
}
