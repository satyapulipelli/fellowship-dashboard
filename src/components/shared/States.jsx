/** Loading, error and empty states, shared by every tab. */

export function Card({ title, subtitle, children, className = '', actions }) {
  return (
    <section className={`card ${className}`}>
      {(title || actions) && (
        <header className="card-header flex items-start justify-between gap-3">
          <div>
            {title && <h2 className="card-title">{title}</h2>}
            <div className="accent-bar" />
            {subtitle && (
              <p className="mt-1.5 text-[0.72rem] leading-snug text-muted">{subtitle}</p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className="p-4">{children}</div>
    </section>
  )
}

export function Skeleton({ height = 320, label = 'Loading' }) {
  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className="flex animate-pulse items-center justify-center rounded border border-nu-gray-100 bg-nu-gray-50"
      style={{ height }}
    >
      <span className="text-[0.75rem] text-muted">{label}…</span>
    </div>
  )
}

export function ErrorState({ error, onRetry }) {
  return (
    <div
      role="alert"
      className="rounded border border-bad/40 bg-bad/5 px-4 py-6 text-center"
    >
      <p className="text-[0.85rem] font-bold text-nu-gray-900">Could not load data</p>
      <p className="mx-auto mt-1 max-w-md text-[0.75rem] leading-snug text-nu-gray-700">
        {error?.message || 'Unknown error.'}
      </p>
      <p className="mx-auto mt-2 max-w-md text-[0.7rem] leading-snug text-muted">
        The dashboard reads static JSON from <code>/data</code>. If this persists, the
        generator may not have been run — see the README.
      </p>
      {onRetry && (
        <button type="button" onClick={onRetry} className="btn mt-3">
          Try again
        </button>
      )}
    </div>
  )
}

export function Empty({ children }) {
  return <p className="empty-text">{children}</p>
}

/**
 * The original showed a notification when the unfiltered catalog was large
 * (server.py:49-54: "N courses detected. Select a program or department for clearer
 * visualization!"). The layered graph is ~11,400px wide unfiltered, so the same nudge is
 * worth keeping.
 */
export function FilterNudge({ count, onFocusFilters }) {
  return (
    <div className="mb-3 flex items-start gap-2 rounded border border-nu-blue/30 bg-nu-blue/5 px-3 py-2">
      <svg
        width="14"
        height="14"
        viewBox="0 0 20 20"
        fill="currentColor"
        className="mt-0.5 shrink-0 text-nu-blue"
        aria-hidden="true"
      >
        <path d="M10 2a8 8 0 100 16 8 8 0 000-16zm1 12H9v-2h2v2zm0-3H9V6h2v5z" />
      </svg>
      <p className="text-[0.75rem] leading-snug text-nu-gray-900">
        <strong>{count.toLocaleString()} courses</strong> in view. Select a program or
        department for a clearer picture — the full catalog spans four levels and is very
        wide.
        {onFocusFilters && (
          <>
            {' '}
            <button
              type="button"
              onClick={onFocusFilters}
              className="font-bold text-nu-blue underline"
            >
              Open filters
            </button>
          </>
        )}
      </p>
    </div>
  )
}
