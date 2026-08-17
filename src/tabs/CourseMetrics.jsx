import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import { InfoTip } from '../components/shared/Tooltip'
import PlotlyChart from '../components/charts/PlotlyChart'
import { CHROME, SEMANTIC, LEVEL_COLORS } from '../styles/palette'
import {
  bottleneckFlags,
  termDisplay,
  int,
  pct,
  num,
} from '../utils/dataTransforms'

export default function CourseMetrics({ filters }) {
  const { data, loading, error, reload } = useData([
    'courses.json',
    'enrollment_by_course.json',
    'programs.json',
    'bottleneck_scores.json',
  ])

  const [search, setSearch] = useState('')
  const [expanded, setExpanded] = useState(null)

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading course metrics" />

  const { courses, enrollment_by_course: enrollment, programs, bottleneck_scores } = data
  const scores = bottleneck_scores?.scores || {}

  return (
    <CourseMetricsInner
      courses={courses}
      enrollment={enrollment}
      programs={programs}
      scores={scores}
      filters={filters}
      search={search}
      setSearch={setSearch}
      expanded={expanded}
      setExpanded={setExpanded}
    />
  )
}

function CourseMetricsInner({
  courses,
  enrollment,
  programs,
  scores,
  filters,
  search,
  setSearch,
  expanded,
  setExpanded,
}) {
  const courseList = useMemo(() => {
    let list = Object.keys(courses)

    if (filters.department !== 'all') {
      list = list.filter((c) => c.startsWith(filters.department + ' '))
    }

    if (search.trim()) {
      const q = search.toLowerCase()
      list = list.filter(
        (c) =>
          c.toLowerCase().includes(q) ||
          courses[c].title.toLowerCase().includes(q),
      )
    }

    list.sort((a, b) => (scores[b] ?? 0) - (scores[a] ?? 0) || a.localeCompare(b))
    return list
  }, [courses, filters, search, scores])

  return (
    <div>
      <header className="mb-4">
        <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
          Course Metrics
        </h2>
        <div className="accent-bar" />
        <p className="mt-1 text-[0.8rem] text-muted">
          Enrollment trends and bottleneck flags per course. {courseList.length} courses in view.
        </p>
      </header>

      <div className="mb-4">
        <input
          type="search"
          placeholder="Search courses…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="select max-w-sm"
        />
      </div>

      {courseList.length === 0 ? (
        <Empty>No courses match the current filters.</Empty>
      ) : (
        <div className="space-y-3">
          {courseList.slice(0, 50).map((code) => (
            <CourseCard
              key={code}
              code={code}
              course={courses[code]}
              enroll={enrollment[code]}
              score={scores[code] ?? 0}
              programs={programs}
              expanded={expanded === code}
              onToggle={() => setExpanded(expanded === code ? null : code)}
            />
          ))}
          {courseList.length > 50 && (
            <p className="py-4 text-center text-[0.75rem] text-muted">
              Showing 50 of {courseList.length} courses. Use search or filters to narrow.
            </p>
          )}
        </div>
      )}
    </div>
  )
}

function CourseCard({ code, course, enroll, score, programs, expanded, onToggle }) {
  const flags = bottleneckFlags(code, enroll, course.program_count, { [code]: score })
  const series = enroll?.enrollment_series
  const hasPlottable = series && series.terms.length >= 2

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={onToggle}
          className="text-left"
        >
          <span className="text-[0.875rem] font-black text-nu-gray-900">{code}</span>
          <span className="ml-2 text-[0.8125rem] text-nu-gray-700">{course.title}</span>
          <span className="ml-2 text-[0.72rem] text-muted">
            Level {course.level} · {course.credits} cr
          </span>
        </button>
        {score >= 0.5 && <span className="badge-bad">Bottleneck</span>}
      </div>

      {flags.length > 0 && (
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className="text-[0.7rem] font-bold text-nu-gray-700">
            Flags
            <InfoTip text="Indicators that this course may constrain student progress." />
          </span>
          {flags.map((f) => (
            <span key={f} className="chip text-[0.65rem]">
              {f}
            </span>
          ))}
        </div>
      )}

      {expanded && (
        <div className="mt-3 border-t border-nu-gray-100 pt-3">
          <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2 lg:grid-cols-3">
            <Row label="Avg enrollment" value={num(enroll?.avg_enrollment, 1)} />
            <Row
              label="Avg Fill Rate"
              tip="Average proportion of seats filled."
              value={pct(enroll?.avg_fill_rate)}
            />
            <Row label="Max fill rate" value={pct(enroll?.max_fill_rate)} />
            <Row
              label="Waitlist Frequency"
              tip="Proportion of offerings with a waitlist."
              value={pct(enroll?.waitlist_frequency)}
            />
            <Row
              label="Sections/Semester"
              tip="Average number of sections offered per semester."
              value={num(enroll?.sections_per_semester, 1)}
            />
            <Row
              label="Offering Frequency"
              tip="Proportion of semesters the course is offered."
              value={num(enroll?.offering_frequency, 2)}
            />
            <Row label="Enrollment trend" value={num(enroll?.enrollment_trend, 2)} />
            <Row label="RF Score" value={num(score, 3)} />
            <Row
              label="Programs"
              tip="Programs that require this course."
              value={course.program_count}
            />
          </div>

          {course.programs && course.programs.length > 0 && (
            <details className="mt-2">
              <summary className="cursor-pointer text-[0.72rem] font-bold text-muted">
                {course.programs.length} program{course.programs.length !== 1 ? 's' : ''}
              </summary>
              <ul className="mt-1 columns-2 text-[0.72rem] text-nu-gray-700">
                {course.programs.map((p) => (
                  <li key={p}>{programs.programs[p]?.program_title || p}</li>
                ))}
              </ul>
            </details>
          )}

          {hasPlottable && (
            <div className="mt-3">
              <EnrollmentTrend series={series} />
            </div>
          )}
        </div>
      )}
    </Card>
  )
}

function Row({ label, value, tip }) {
  return (
    <div className="stat-row">
      <span className="stat-label">
        {label}
        {tip && <InfoTip text={tip} />}
      </span>
      <span className="stat-value">{value}</span>
    </div>
  )
}

function EnrollmentTrend({ series }) {
  const labels = series.term_labels || series.terms.map(termDisplay)
  const x = labels
  const y = series.enrollment

  const n = x.length
  const xIdx = Array.from({ length: n }, (_, i) => i)
  const sumX = xIdx.reduce((a, b) => a + b, 0)
  const sumY = y.reduce((a, b) => a + b, 0)
  const sumXY = xIdx.reduce((a, i) => a + i * y[i], 0)
  const sumXX = xIdx.reduce((a, i) => a + i * i, 0)
  const slope = (n * sumXY - sumX * sumY) / (n * sumXX - sumX * sumX || 1)
  const intercept = (sumY - slope * sumX) / n
  const trendY = xIdx.map((i) => slope * i + intercept)

  return (
    <PlotlyChart
      data={[
        {
          x,
          y,
          mode: 'markers',
          type: 'scatter',
          marker: { color: CHROME.blue, size: 6 },
          name: 'Enrollment',
          hovertemplate: '%{x}: %{y}<extra></extra>',
        },
        {
          x,
          y: trendY,
          mode: 'lines',
          type: 'scatter',
          line: { color: SEMANTIC.muted, dash: 'dash', width: 1.5 },
          name: 'Trend',
          hoverinfo: 'skip',
        },
      ]}
      layout={{
        xaxis: { title: { text: '' }, tickangle: -45 },
        yaxis: { title: { text: 'Enrollment' } },
        margin: { l: 48, r: 16, t: 8, b: 56 },
        showlegend: false,
      }}
      height={260}
    />
  )
}
