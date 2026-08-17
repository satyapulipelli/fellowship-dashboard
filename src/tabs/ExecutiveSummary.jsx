import { useMemo } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import PlotlyChart from '../components/charts/PlotlyChart'
import { CHROME, SEMANTIC, DEPARTMENT_FALLBACK, SCALES } from '../styles/palette'
import { int, pct } from '../utils/dataTransforms'

export default function ExecutiveSummary() {
  const { data, loading, error, reload } = useData([
    'summary_stats.json',
    'department_metrics.json',
    'bottleneck_scores.json',
  ])

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading executive summary" />

  const { summary_stats: summary, department_metrics: depts, bottleneck_scores } = data
  const k = summary.kpis || {}
  const fillHist = summary.fill_rate_histogram
  const scores = bottleneck_scores?.scores || {}

  return (
    <div>
      <header className="mb-5">
        <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
          Executive Summary
        </h2>
        <div className="accent-bar" />
        <p className="mt-1 text-[0.8rem] text-muted">
          Institution-wide curriculum structure and enrollment capacity at a glance.
        </p>
      </header>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <KpiCard label="Total Courses" value={int(k.total_courses)} />
        <KpiCard label="Total Programs" value={int(k.total_programs)} />
        <KpiCard
          label="At Capacity"
          value={`${k.pct_at_capacity}%`}
          tone={k.pct_at_capacity >= 35 ? 'bad' : 'ok'}
        />
        <KpiCard
          label="With Waitlist"
          value={`${k.pct_with_waitlist}%`}
          tone={k.pct_with_waitlist >= 30 ? 'warn' : 'ok'}
        />
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Card title="Fill Rate Distribution">
          <FillRateHistogram bins={fillHist} />
        </Card>
        <Card title="Department Size">
          <DepartmentBar depts={depts} scores={scores} />
        </Card>
      </div>

      <div className="mt-5 grid gap-4 lg:grid-cols-2">
        <Card title="Enrollment Overview">
          <div className="space-y-0">
            <StatRow label="Total sections" value={int(k.total_sections)} />
            <StatRow label="Mean fill rate" value={pct(k.mean_fill_rate)} />
            <StatRow label="At capacity" value={`${k.pct_at_capacity}%`} />
            <StatRow label="With waitlist" value={`${k.pct_with_waitlist}%`} />
            <StatRow label="Bottleneck courses" value={int(k.bottleneck_courses)} />
          </div>
        </Card>
        <Card title="Capacity Distribution">
          <CapacityDonut
            atCapacity={k.pct_at_capacity}
            withWaitlist={k.pct_with_waitlist}
          />
        </Card>
      </div>
    </div>
  )
}

function KpiCard({ label, value, tone = 'default' }) {
  const bg =
    tone === 'bad'
      ? 'border-l-4 border-l-bad'
      : tone === 'warn'
        ? 'border-l-4 border-l-warn'
        : tone === 'ok'
          ? 'border-l-4 border-l-ok'
          : ''
  return (
    <div className={`card px-4 py-3 ${bg}`}>
      <div className="text-[1.5rem] font-black leading-tight tabular-nums text-nu-gray-900">
        {value}
      </div>
      <div className="mt-0.5 text-[0.72rem] font-bold uppercase tracking-wide text-muted">
        {label}
      </div>
    </div>
  )
}

function StatRow({ label, value }) {
  return (
    <div className="stat-row">
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
    </div>
  )
}

function FillRateHistogram({ bins }) {
  if (!bins?.counts) return <Empty>No histogram data</Empty>
  return (
    <PlotlyChart
      data={[
        {
          x: bins.bin_edges.slice(0, -1).map((e) => `${(e * 100).toFixed(0)}%`),
          y: bins.counts,
          type: 'bar',
          marker: { color: CHROME.blue, opacity: 0.85 },
          hovertemplate: '%{x}: %{y} courses<extra></extra>',
        },
      ]}
      layout={{
        xaxis: { title: { text: 'Fill Rate' } },
        yaxis: { title: { text: 'Courses' } },
        margin: { l: 48, r: 16, t: 16, b: 48 },
      }}
      height={260}
    />
  )
}

function DepartmentBar({ depts, scores }) {
  const entries = Object.entries(depts).sort(
    (a, b) => (b[1].n_courses ?? 0) - (a[1].n_courses ?? 0),
  )

  const bottleneckCounts = useMemo(() => {
    const counts = {}
    for (const [code, score] of Object.entries(scores)) {
      const dept = code.split(' ')[0]
      if (!counts[dept]) counts[dept] = 0
      if (score >= 0.5) counts[dept]++
    }
    return counts
  }, [scores])

  const codes = entries.map(([code]) => code)
  const totals = entries.map(([, d]) => d.n_courses ?? 0)
  const bottlenecks = codes.map((code) => bottleneckCounts[code] ?? 0)
  const nonBottlenecks = totals.map((t, i) => t - bottlenecks[i])
  const colors = codes.map(
    ([code]) => depts[code]?.color || DEPARTMENT_FALLBACK[code] || CHROME.gray700,
  )

  return (
    <PlotlyChart
      data={[
        {
          x: codes,
          y: nonBottlenecks,
          name: 'Non-bottleneck',
          type: 'bar',
          marker: {
            color: codes.map(
              (code) => depts[code]?.color || DEPARTMENT_FALLBACK[code] || CHROME.gray700,
            ),
            opacity: 0.85,
          },
          hovertemplate: '%{x}: %{y} non-bottleneck<extra></extra>',
        },
        {
          x: codes,
          y: bottlenecks,
          name: 'Bottleneck',
          type: 'bar',
          marker: { color: SEMANTIC.bad, opacity: 0.9 },
          hovertemplate: '%{x}: %{y} bottleneck<extra></extra>',
        },
      ]}
      layout={{
        barmode: 'stack',
        xaxis: { title: { text: 'Department' } },
        yaxis: { title: { text: 'Courses' } },
        margin: { l: 48, r: 16, t: 16, b: 48 },
        legend: { orientation: 'h', x: 0.5, xanchor: 'center', y: 1.08 },
      }}
      height={260}
    />
  )
}

function CapacityDonut({ atCapacity, withWaitlist }) {
  const remainder = 100 - atCapacity
  return (
    <PlotlyChart
      data={[
        {
          values: [atCapacity, remainder],
          labels: ['At/Over Capacity', 'Under Capacity'],
          type: 'pie',
          hole: 0.55,
          marker: { colors: [SEMANTIC.bad, CHROME.gray200] },
          textinfo: 'percent',
          hovertemplate: '%{label}: %{value:.1f}%<extra></extra>',
        },
      ]}
      layout={{ margin: { l: 16, r: 16, t: 16, b: 16 }, showlegend: true }}
      height={240}
    />
  )
}
