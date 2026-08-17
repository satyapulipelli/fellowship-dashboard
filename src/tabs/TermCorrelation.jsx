import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import { InfoTip } from '../components/shared/Tooltip'
import PlotlyChart from '../components/charts/PlotlyChart'
import { CHROME, SEMANTIC } from '../styles/palette'
import { num, pct } from '../utils/dataTransforms'

export default function TermCorrelation() {
  const { data, loading, error, reload } = useData([
    'department_responsiveness.json',
    'department_metrics.json',
  ])

  const [selectedDept, setSelectedDept] = useState(null)

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading term correlation" />

  const { department_responsiveness: resp, department_metrics: deptMeta } = data
  const departments = resp.departments || {}
  const ranking = resp.ranking || Object.keys(departments).sort()

  return (
    <div>
      <header className="mb-4">
        <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
          Term-to-Term Correlation
        </h2>
        <div className="accent-bar" />
        <p className="mt-1 text-[0.8rem] text-muted">
          {resp.formula}
        </p>
      </header>

      <Card title={<>Department Responsiveness<InfoTip text="Measures how well each department adjusts capacity in response to enrollment demand. Higher scores indicate departments that effectively add sections or seats when demand increases." /></>}>
        <ResponsivenessChart departments={departments} ranking={ranking} />
      </Card>

      <div className="mt-4">
        <Card title="Responsiveness Scores">
          <div className="overflow-x-auto">
            <table className="w-full text-[0.75rem]">
              <thead>
                <tr className="border-b border-nu-gray-200 text-left text-[0.7rem] font-bold uppercase text-muted">
                  <th className="px-2 py-1.5">Department</th>
                  <th className="px-2 py-1.5 text-right">Score</th>
                  <th className="px-2 py-1.5 text-right">Utilization</th>
                  <th className="px-2 py-1.5 text-right">Over-cap</th>
                  <th className="px-2 py-1.5 text-right">Waitlist</th>
                  <th className="px-2 py-1.5 text-right">Correlation</th>
                  <th className="px-2 py-1.5">Class</th>
                </tr>
              </thead>
              <tbody>
                {ranking.map((code) => {
                  const d = departments[code] || {}
                  const comp = d.components || {}
                  const cls = d.classification || '—'
                  return (
                    <tr
                      key={code}
                      className={`border-b border-nu-gray-100 cursor-pointer hover:bg-nu-gray-50 ${
                        selectedDept === code ? 'bg-nu-blue/5' : ''
                      }`}
                      onClick={() => setSelectedDept(selectedDept === code ? null : code)}
                    >
                      <td className="px-2 py-1.5 font-bold">
                        {d.department_name || code}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(d.responsiveness_score, 3)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {pct(comp.utilization)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {pct(comp.over_capacity_rate)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {pct(comp.waitlist_rate)}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {num(d.correlation, 3)}
                      </td>
                      <td className="px-2 py-1.5">
                        <ClassBadge cls={cls} />
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          {resp.scoring_note && (
            <p className="mt-3 px-2 text-[0.7rem] leading-snug text-muted">{resp.scoring_note}</p>
          )}
        </Card>
      </div>

      {selectedDept && departments[selectedDept]?.term_pairs && (
        <div className="mt-4">
          <Card
            title={`${departments[selectedDept].department_name || selectedDept} — Year-over-Year`}
          >
            <div className="overflow-x-auto">
              <table className="w-full text-[0.75rem]">
                <thead>
                  <tr className="border-b border-nu-gray-200 text-left text-[0.7rem] font-bold uppercase text-muted">
                    <th className="px-2 py-1.5">Period</th>
                    <th className="px-2 py-1.5 text-right">Courses</th>
                    <th className="px-2 py-1.5 text-right">Correlation</th>
                    <th className="px-2 py-1.5 text-right">Demand-Resp</th>
                    <th className="px-2 py-1.5 text-right">Enrollment</th>
                    <th className="px-2 py-1.5 text-right">Next Capacity</th>
                    <th className="px-2 py-1.5 text-right">Unmet Demand</th>
                    <th className="px-2 py-1.5 text-right">Cap Added</th>
                  </tr>
                </thead>
                <tbody>
                  {departments[selectedDept].term_pairs.map((p, i) => (
                    <tr key={i} className="border-b border-nu-gray-100 hover:bg-nu-gray-50">
                      <td className="px-2 py-1.5 font-bold">
                        {p.year_n_label} → {p.year_n_plus_1_label}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{p.n_courses}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{num(p.correlation, 3)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">{num(p.demand_response_correlation, 3)}</td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {p.total_enrollment_year_n?.toLocaleString()}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {p.total_capacity_year_n_plus_1?.toLocaleString()}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        {p.total_unmet_demand_year_n?.toLocaleString()}
                      </td>
                      <td className="px-2 py-1.5 text-right tabular-nums">
                        <span className={p.total_capacity_added > 0 ? 'text-ok font-bold' : p.total_capacity_added < 0 ? 'text-bad font-bold' : ''}>
                          {p.total_capacity_added > 0 ? '+' : ''}{p.total_capacity_added?.toLocaleString()}
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

function ResponsivenessChart({ departments, ranking }) {
  const codes = ranking
  const scores = codes.map((d) => departments[d]?.responsiveness_score ?? 0)
  const classes = codes.map((d) => departments[d]?.classification ?? '')

  const colors = classes.map((c) =>
    c === 'responsive' ? SEMANTIC.ok : c === 'strained' ? SEMANTIC.warn : SEMANTIC.bad,
  )

  return (
    <PlotlyChart
      data={[
        {
          x: codes,
          y: scores,
          type: 'bar',
          marker: { color: colors },
          hovertemplate: '%{x}: %{y:.3f} (%{customdata})<extra></extra>',
          customdata: classes,
        },
      ]}
      layout={{
        xaxis: { title: { text: 'Department' } },
        yaxis: { title: { text: 'Responsiveness Score' }, range: [0, 1] },
        margin: { l: 48, r: 16, t: 16, b: 48 },
        shapes: [
          {
            type: 'line',
            xref: 'paper',
            x0: 0, x1: 1, y0: 0.5, y1: 0.5,
            line: { color: SEMANTIC.muted, dash: 'dot', width: 1 },
          },
        ],
      }}
      height={320}
    />
  )
}

function ClassBadge({ cls }) {
  const style =
    cls === 'responsive'
      ? 'bg-ok/15 text-ok'
      : cls === 'strained'
        ? 'bg-warn/15 text-nu-gray-900'
        : 'bg-bad/15 text-bad'
  return (
    <span className={`inline-block rounded px-1.5 py-0.5 text-[0.65rem] font-bold ${style}`}>
      {cls}
    </span>
  )
}
