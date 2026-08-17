/**
 * Custom Plotly bundle.
 *
 * The full plotly.js dist is ~4.5 MB minified because it carries 3D, maps, financial and
 * scientific trace types this dashboard never uses. Registering only what the eight tabs
 * need against plotly.js/lib/core cuts that substantially.
 *
 * Traces, and which tab needs each:
 *   scatter      Graph View (nodes + edges), Course Metrics (enrollment trend),
 *                Redundancy (bottleneck -> substitute network), Term Correlation
 *   bar          Department comparisons, responsiveness ranking, capacity shortfalls
 *   heatmap      Temporal Analysis, similarity matrix
 *   pie          Executive Summary capacity donut
 *   histogram    Executive Summary fill-rate distribution
 *   scatterpolar Program Metrics radar comparison
 *
 * If a tab later needs another trace type, add it here — an unregistered type fails at
 * render with "Trace type 'x' not found".
 */
import Plotly from 'plotly.js/lib/core'

import scatter from 'plotly.js/lib/scatter'
import bar from 'plotly.js/lib/bar'
import heatmap from 'plotly.js/lib/heatmap'
import pie from 'plotly.js/lib/pie'
import histogram from 'plotly.js/lib/histogram'
import scatterpolar from 'plotly.js/lib/scatterpolar'

import createPlotlyComponent from 'react-plotly.js/factory'

Plotly.register([scatter, bar, heatmap, pie, histogram, scatterpolar])

export const Plot = createPlotlyComponent(Plotly)
export default Plotly
