import { useMemo, useState } from 'react'
import { useData } from '../hooks/useData'
import { Card, Skeleton, ErrorState, Empty } from '../components/shared/States'
import { InfoTip } from '../components/shared/Tooltip'
import { CHROME, LEVEL_COLORS } from '../styles/palette'
import { int, pct, num } from '../utils/dataTransforms'

export default function ProgramMetrics({ filters }) {
  const { data, loading, error, reload } = useData([
    'program_structures.json',
  ])

  const [sortBy, setSortBy] = useState('max_depth')

  if (error) return <ErrorState error={error} onRetry={reload} />
  if (loading) return <Skeleton height={500} label="Loading program metrics" />

  const { program_structures: structures } = data

  return (
    <ProgramMetricsInner
      structures={structures}
      filters={filters}
      sortBy={sortBy}
      setSortBy={setSortBy}
    />
  )
}

function ProgramMetricsInner({ structures, filters, sortBy, setSortBy }) {
  const programList = useMemo(() => {
    const reqMode = structures.required_mode || {}
    let list = Object.entries(reqMode)

    if (filters.program !== 'all') {
      list = list.filter(([code]) => code === filters.program)
    } else if (filters.department !== 'all') {
      list = list.filter(([, m]) => m.department === filters.department)
    }

    list.sort((a, b) => {
      const av = a[1][sortBy] ?? 0
      const bv = b[1][sortBy] ?? 0
      return bv - av
    })

    return list
  }, [structures, filters, sortBy])

  if (programList.length === 0) return <Empty>No programs match the current filters.</Empty>

  const allMode = structures.all_mode || {}

  return (
    <div>
      <header className="mb-4 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-black tracking-tight text-nu-gray-900">
            Program Metrics
          </h2>
          <div className="accent-bar" />
          <p className="mt-1 text-[0.8rem] text-muted">
            Structural comparison across {programList.length} program{programList.length !== 1 ? 's' : ''}.
          </p>
        </div>
        <select
          className="select w-auto"
          value={sortBy}
          onChange={(e) => setSortBy(e.target.value)}
        >
          <option value="max_depth">Sort by depth</option>
          <option value="total_courses">Sort by course count</option>
          <option value="num_connections">Sort by connections</option>
          <option value="density">Sort by density</option>
        </select>
      </header>

      <div className="space-y-4">
        {programList.map(([code, metrics]) => (
          <ProgramCard
            key={code}
            code={code}
            metrics={metrics}
            allMetrics={allMode[code]}
          />
        ))}
      </div>
    </div>
  )
}

function ProgramCard({ code, metrics, allMetrics }) {
  if (!metrics) return null

  return (
    <Card
      title={metrics.program_title || code}
      subtitle={`${code} · ${metrics.degree_type || ''}`}
    >
      <div className="grid gap-x-8 gap-y-0 sm:grid-cols-2 lg:grid-cols-3">
        <StatRow
          label="Total Courses"
          tip="Total number of courses currently included in this program's required curriculum."
          value={metrics.total_courses}
        />
        <StatRow
          label="Total Dependencies"
          tip="Total number of prerequisite relationships between required courses in this program."
          value={metrics.num_connections}
        />
        <StatRow
          label="Program Depth"
          tip="Length of the longest internal prerequisite chain within the program. This represents the maximum number of sequential required courses a student must complete."
          value={metrics.max_depth}
        />
        <StatRow
          label="Avg Prereqs per Course"
          tip="Average number of prerequisites per course within this program. Higher values indicate a more sequential curriculum."
          value={num(metrics.avg_prereqs)}
        />
        <StatRow
          label="Density Score"
          tip="How interconnected the program's courses are, relative to the maximum possible number of prerequisite connections. Higher values mean courses depend more heavily on each other."
          value={num(metrics.density, 4)}
        />
        <StatRow
          label="Cross-Program Share"
          tip="Proportion of required courses that are shared with at least one other program. Higher values indicate more overlap with other programs' curricula."
          value={pct(metrics.cross_program_share)}
        />
        <StatRow
          label="Avg Unlock Potential"
          tip="Average number of other required courses that each course unlocks as a prerequisite. Higher values indicate courses that enable progress to many other required courses."
          value={num(metrics.avg_unlocks)}
        />
        <StatRow
          label="Foundational Ratio"
          tip="Proportion of courses that are lower-level (1000–3000 level). Higher values suggest a stronger emphasis on foundational coursework early in the program."
          value={pct(metrics.foundational_ratio)}
        />
        <StatRow
          label="Modularity Proxy"
          tip="Number of disconnected course groups within the required-course network. Higher values mean the curriculum has more independent clusters."
          value={metrics.modularity_proxy}
        />
        <StatRow
          label="Max Prerequisites"
          tip="Maximum number of prerequisites required by any single course in this program."
          value={metrics.max_prereqs}
        />
        <StatRow
          label="Cross-Dept %"
          value={`${num(metrics.cross_dept_pct, 1)}%`}
        />
        <StatRow label="Gateway Courses" value={metrics.gateway_count} />
      </div>

      {metrics.level_ratios && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {Object.entries(metrics.level_ratios)
            .sort(([a], [b]) => a - b)
            .map(([level, pctVal]) => (
              <span
                key={level}
                className="inline-flex items-center gap-1.5 rounded px-1.5 py-0.5 text-[0.65rem] font-bold"
                style={{
                  backgroundColor: `${LEVEL_COLORS[level] || CHROME.gray400}20`,
                  color: LEVEL_COLORS[level] || CHROME.gray700,
                }}
              >
                <span
                  className="inline-block h-2 w-2 rounded-full"
                  style={{ backgroundColor: LEVEL_COLORS[level] || CHROME.gray700 }}
                />
                {level}000: {num(pctVal, 1)}%
              </span>
            ))}
        </div>
      )}

      {metrics.bottleneck_courses?.length > 0 && (
        <div className="mt-2">
          <span className="text-[0.72rem] font-bold text-nu-gray-700">
            Bottleneck Courses
            <InfoTip text="Courses identified as bottlenecks by the ML pipeline within this program's required curriculum. High scores indicate courses where students experience delays or pathway stalling." />
          </span>
          <p className="text-[0.7rem] text-muted">
            {metrics.bottleneck_courses.join(', ')}
          </p>
        </div>
      )}

      {allMetrics && allMetrics.total_courses !== metrics.total_courses && (
        <p className="mt-1 text-[0.7rem] text-muted">
          With electives: {allMetrics.total_courses} courses, depth {allMetrics.max_depth}
        </p>
      )}
    </Card>
  )
}

function StatRow({ label, value, tip }) {
  return (
    <div className="stat-row">
      <span className="stat-label">
        {label}
        {tip && <InfoTip text={tip} />}
      </span>
      <span className="stat-value">{value ?? '—'}</span>
    </div>
  )
}
