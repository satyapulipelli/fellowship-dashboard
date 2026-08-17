import { useMemo } from 'react'
import { Plot } from './plotly'
import { BASE_LAYOUT, BASE_CONFIG } from '../../styles/palette'

/**
 * Wrapper applying the shared layout and config so every chart sits in the page the same
 * way. Callers pass only what differs.
 *
 * `layout` and `config` are merged shallowly, with `xaxis`/`yaxis`/`font`/`margin` merged
 * one level deeper — those are the ones callers routinely want to extend rather than
 * replace.
 */
export default function PlotlyChart({
  data,
  layout = {},
  config = {},
  height = 420,
  className = '',
  onClick,
  onHover,
  ...rest
}) {
  const mergedLayout = useMemo(
    () => ({
      ...BASE_LAYOUT,
      ...layout,
      height,
      font: { ...BASE_LAYOUT.font, ...(layout.font || {}) },
      margin: { ...BASE_LAYOUT.margin, ...(layout.margin || {}) },
      hoverlabel: { ...BASE_LAYOUT.hoverlabel, ...(layout.hoverlabel || {}) },
      xaxis: { ...BASE_LAYOUT.xaxis, ...(layout.xaxis || {}) },
      yaxis: { ...BASE_LAYOUT.yaxis, ...(layout.yaxis || {}) },
    }),
    [layout, height],
  )

  const mergedConfig = useMemo(() => ({ ...BASE_CONFIG, ...config }), [config])

  return (
    <Plot
      data={data}
      layout={mergedLayout}
      config={mergedConfig}
      onClick={onClick}
      onHover={onHover}
      className={`w-full ${className}`}
      style={{ width: '100%', height: `${height}px` }}
      useResizeHandler
      {...rest}
    />
  )
}
