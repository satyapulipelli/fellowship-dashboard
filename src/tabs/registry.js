/**
 * Tab registry.
 *
 * Grouped by provenance, which is also a sensible reading order:
 *
 *   Overview            an entry point that grounds the numbers
 *   Curriculum          the four tabs that were live in the Python Shiny dashboard,
 *                       in the original's own order, plus Demand Forecast (coded in the
 *                       original but disabled for want of a preference feed)
 *   Enrollment          the tabs from the superseded Plotly Dash dashboard
 *
 * `id` values match the original's nav_panel `value=` where one existed, so the mapping
 * back to the source stays obvious.
 *
 * `files` drives lazy loading — only these are fetched when the tab opens.
 */

export const TABS = [
  {
    id: 'executive_summary',
    label: 'Executive Summary',
    group: 'Overview',
    blurb: 'Institution-wide capacity and structure at a glance',
    files: ['summary_stats.json', 'department_metrics.json'],
    usesFilters: false,
  },
  {
    id: 'graph_view',
    label: 'Graph View',
    group: 'Curriculum Structure',
    blurb: 'Prerequisite network, bottlenecks, and cascade impact',
    files: ['courses.json', 'prerequisites.json', 'programs.json', 'terms.json'],
    usesFilters: true,
    original: 'main_view/graph_view',
  },
  {
    id: 'program_metrics',
    label: 'Program Metrics',
    group: 'Curriculum Structure',
    blurb: 'Structural comparison across programs',
    files: ['program_structures.json', 'programs.json', 'courses.json'],
    usesFilters: true,
    original: 'main_view/program_metrics',
  },
  {
    id: 'course_metrics',
    label: 'Course Metrics',
    group: 'Curriculum Structure',
    blurb: 'Enrollment trends and bottleneck flags per course',
    files: [
      'courses.json',
      'enrollment_by_course.json',
      'programs.json',
      'bottleneck_scores.json',
    ],
    usesFilters: true,
    original: 'main_view/course_metrics',
  },
  {
    id: 'redundancy_analysis',
    label: 'Redundancy Analysis',
    group: 'Curriculum Structure',
    blurb: 'Content-equivalent alternatives to bottleneck courses',
    files: ['similarity_pairs.json', 'courses.json', 'bottleneck_scores.json'],
    usesFilters: true,
    original: 'main_view/redundancy_analysis',
  },
  {
    id: 'demand_forecast',
    label: 'Demand Forecast',
    group: 'Curriculum Structure',
    blurb: 'Capacity shortfalls under enrollment growth scenarios',
    files: ['forecast_scenarios.json', 'courses.json', 'department_metrics.json'],
    usesFilters: true,
    original: 'main_view/admin_demand (disabled in the original)',
  },
  {
    id: 'temporal_analysis',
    label: 'Temporal Analysis',
    group: 'Enrollment Analytics',
    blurb: 'Seasonal patterns and like-for-like term comparisons',
    files: ['temporal_patterns.json', 'department_metrics.json'],
    usesFilters: false,
  },
  {
    id: 'term_correlation',
    label: 'Term-to-Term Correlation',
    group: 'Enrollment Analytics',
    blurb: 'How well do departments respond to demand?',
    files: ['department_responsiveness.json', 'department_metrics.json'],
    usesFilters: false,
  },
]

export const TAB_GROUPS = [...new Set(TABS.map((t) => t.group))]

export const DEFAULT_TAB = 'executive_summary'

export function getTab(id) {
  return TABS.find((t) => t.id === id) || TABS[0]
}
