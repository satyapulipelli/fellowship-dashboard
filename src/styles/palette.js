/**
 * Chart palette, as JS values for Plotly.
 *
 * Every value here is copied from the original Shiny dashboard's graphs.py and
 * redundancy_visualizations.py. None of it was institutionally branded — it is a generic
 * Tailwind-family palette — so it transfers unchanged. The Northeastern chrome tokens
 * live in index.css under @theme.
 */

// ── Chrome (mirrors @theme, for the few places Plotly needs the value directly) ──
export const CHROME = {
  red: '#c8102e',
  gold: '#c8a978',
  blue: '#0033a0',
  gray50: '#f8f9fa',
  gray100: '#e9ecef',
  gray200: '#dee2e6',
  gray700: '#495057',
  gray900: '#212529',
  white: '#ffffff',
}

// ── Semantic ──
export const SEMANTIC = {
  ok: '#22c55e',
  warn: '#eab308',
  bad: '#dc2626',
  muted: '#64748b',
}

// ── Graph edges (graphs.py edge_style) ──
export const EDGE = {
  prerequisite: { color: '#10b981', dash: 'solid' },
  corequisite: { color: '#f59e0b', dash: 'dash' },
}

// ── Node colours, in the original's priority order (create_plotly_figure) ──
export const NODE = {
  removed: '#374151',
  greyed: '#d1d5db', // downstream of a removed course
  bottleneck: '#dc2626',
  dimmed: '#808080', // non-bottleneck while highlighting bottlenecks
}

/** graphs.py level_colors */
export const LEVEL_COLORS = {
  0: '#6b7280',
  1: '#22c55e',
  2: '#eab308',
  3: '#f59e0b',
  4: '#ef4444',
  5: '#3b82f6',
  6: '#8b5cf6',
  7: '#ec4899',
}

/** graphs.py program_color — number of programs sharing a course */
export function programColor(count) {
  if (count <= 0) return '#9ca3af'
  if (count === 1) return '#3b82f6'
  if (count === 2) return '#8b5cf6'
  if (count === 3) return '#ec4899'
  return '#dc2626'
}

// ── Redundancy tab (redundancy_visualizations.py) ──
export const SUBSTITUTE = {
  better: '#22c55e', // is_better_access
  neutral: '#64748b',
}

/**
 * Similarity edge colour. The original lerps grey -> red over
 * t = (similarity - 0.60) / 0.35, rgb(156->220, 163->38, 175->38).
 */
export function similarityColor(similarity) {
  const t = Math.max(0, Math.min(1, (similarity - 0.6) / 0.35))
  const r = Math.round(156 + t * (220 - 156))
  const g = Math.round(163 + t * (38 - 163))
  const b = Math.round(175 + t * (38 - 175))
  return `rgb(${r},${g},${b})`
}

// ── Surfaces (graphs.py figure layout) ──
export const SURFACE = {
  plotBg: '#ffffff',
  paperBg: '#f9fafb',
}

/**
 * Sequential scale for heatmaps. The original used Plotly's built-in 'RdYlBu_r' for the
 * similarity matrix; a single-hue teal scale is used for the temporal heatmap so density
 * does not read as a good/bad judgement.
 */
export const SCALES = {
  similarity: 'RdYlBu_r',
  sequential: [
    [0.0, '#f8fafc'],
    [0.25, '#cbd5e1'],
    [0.5, '#7dd3fc'],
    [0.75, '#0284c7'],
    [1.0, '#0c4a6e'],
  ],
  // Diverging, for anything centred on a meaningful midpoint (e.g. fill rate at 1.0)
  diverging: [
    [0.0, '#1d4ed8'],
    [0.5, '#f8fafc'],
    [1.0, '#b91c1c'],
  ],
}

/**
 * Baseline Plotly layout. Values match the original's figure layout so charts sit in the
 * page the same way.
 */
export const BASE_LAYOUT = {
  plot_bgcolor: SURFACE.plotBg,
  paper_bgcolor: SURFACE.paperBg,
  font: { family: 'Lato, system-ui, sans-serif', size: 12, color: CHROME.gray900 },
  margin: { l: 48, r: 24, t: 40, b: 40 },
  hovermode: 'closest',
  hoverlabel: {
    bgcolor: CHROME.white,
    bordercolor: CHROME.gray200,
    font: { family: 'Lato, system-ui, sans-serif', size: 12, color: CHROME.gray900 },
    align: 'left',
  },
  xaxis: { gridcolor: CHROME.gray100, zerolinecolor: CHROME.gray200 },
  yaxis: { gridcolor: CHROME.gray100, zerolinecolor: CHROME.gray200 },
}

/** The original's modebar config (graph_view_server.py) */
export const BASE_CONFIG = {
  displayModeBar: true,
  displaylogo: false,
  modeBarButtonsToRemove: ['lasso2d', 'select2d'],
  responsive: true,
}

/**
 * Department colours also ship per-department in department_metrics.json as `color`.
 * Read them from the data so a department keeps one colour everywhere; this is a
 * fallback for when metrics have not loaded yet.
 *
 * Note COMM is #dc2626, the same as SEMANTIC.bad. Where a chart encodes both department
 * identity and a semantic state, carry the state with shape, opacity or border — not fill.
 */
export const DEPARTMENT_FALLBACK = {
  CS: '#2563eb',
  DS: '#0891b2',
  MATH: '#7c3aed',
  BA: '#c026d3',
  ENGR: '#ea580c',
  ECON: '#65a30d',
  BIO: '#059669',
  PSYC: '#d97706',
  COMM: '#be185d',
  PHYS: '#4f46e5',
}
