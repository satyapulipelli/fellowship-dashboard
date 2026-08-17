import { useEffect, useState, useCallback } from 'react'

/**
 * Lazy per-file data loading.
 *
 * The 14 generated files total 3.6 MB uncompressed, and no single tab needs more than a
 * few of them — enrollment_by_course.json alone is 1 MB and only Course Metrics and the
 * enrollment tabs touch it. Fetching everything up front would put a megabyte of
 * enrollment series in front of a user who opens Graph View and leaves.
 *
 * Files are fetched once and cached for the session, so switching tabs never refetches.
 * In-flight requests are deduplicated, so two components mounting in the same tick share
 * one request.
 */

const cache = new Map() // name -> parsed JSON
const inflight = new Map() // name -> Promise
const listeners = new Set()

function notify() {
  for (const l of listeners) l()
}

export function loadFile(name) {
  if (cache.has(name)) return Promise.resolve(cache.get(name))
  if (inflight.has(name)) return inflight.get(name)

  const p = fetch(`${import.meta.env.BASE_URL}data/${name}`)
    .then((res) => {
      if (!res.ok) throw new Error(`${name}: HTTP ${res.status}`)
      return res.json()
    })
    .then((json) => {
      cache.set(name, json)
      inflight.delete(name)
      notify()
      return json
    })
    .catch((err) => {
      inflight.delete(name)
      throw err
    })

  inflight.set(name, p)
  return p
}

/** Synchronous peek — returns undefined if not yet loaded. */
export function peek(name) {
  return cache.get(name)
}

/**
 * Request one or more data files.
 *
 * @param {string[]} names file names under /data
 * @returns {{data: Object, loading: boolean, error: Error|null, reload: Function}}
 *          `data` is keyed by file name without the .json suffix
 */
export function useData(names) {
  const key = names.join(',')
  const [state, setState] = useState(() => ({
    data: collect(names),
    loading: names.some((n) => !cache.has(n)),
    error: null,
  }))

  const run = useCallback(() => {
    let cancelled = false
    const missing = names.filter((n) => !cache.has(n))

    if (missing.length === 0) {
      setState({ data: collect(names), loading: false, error: null })
      return () => {}
    }

    setState((s) => ({ ...s, loading: true, error: null }))
    Promise.all(missing.map(loadFile))
      .then(() => {
        if (!cancelled) setState({ data: collect(names), loading: false, error: null })
      })
      .catch((error) => {
        if (!cancelled) setState((s) => ({ ...s, loading: false, error }))
      })

    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key])

  useEffect(run, [run])

  return { ...state, reload: run }
}

function collect(names) {
  const out = {}
  for (const n of names) {
    const v = cache.get(n)
    if (v !== undefined) out[n.replace(/\.json$/, '')] = v
  }
  return out
}

/** Warm the cache for files a tab is likely to open next, without blocking. */
export function prefetch(names) {
  for (const n of names) {
    if (!cache.has(n) && !inflight.has(n)) loadFile(n).catch(() => {})
  }
}

/** Every generated file, for reference and for the export tab. */
export const DATA_FILES = [
  'courses.json',
  'prerequisites.json',
  'programs.json',
  'program_structures.json',
  'department_metrics.json',
  'enrollment_by_course.json',
  'bottleneck_scores.json',
  'similarity_pairs.json',
  'forecast_scenarios.json',
  'department_responsiveness.json',
  'temporal_patterns.json',
  'summary_stats.json',
  'terms.json',
  'students_sample.json',
]
