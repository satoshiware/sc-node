import React, { useEffect, useMemo, useState } from 'react'
import ConnectWorkers from './ConnectWorkers'
import {
  FiCheckCircle,
  FiChevronDown,
  FiChevronLeft,
  FiChevronRight,
  FiEye,
  FiPower,
  FiRefreshCw,
  FiSearch,
  FiZap,
} from 'react-icons/fi'

function formatHashrateTh(th) {
  const n = Number(th)
  if (!Number.isFinite(n) || n <= 0) return '0.000 H/s'
  if (n < 0.000001) return `${(n * 1e12).toFixed(3)} H/s`
  return `${n.toFixed(3)} TH/s`
}

function formatAlertLimit(th) {
  const n = Number(th)
  if (!Number.isFinite(n) || n <= 0) return '—'
  if (n >= 1) return `${n.toFixed(3)} TH/s`
  if (n >= 0.001) return `${(n * 1000).toFixed(1)} MH/s`
  return `${(n * 1e6).toFixed(1)} kH/s`
}

function StateCell({ state }) {
  const s = String(state || '').toLowerCase()
  if (s === 'ok') {
    return (
      <span className="inline-flex items-center gap-1.5 text-emerald-400">
        <FiCheckCircle className="w-4 h-4 flex-shrink-0" aria-hidden />
        OK
      </span>
    )
  }
  if (s === 'dis' || s === 'disabled') {
    return (
      <span className="inline-flex items-center gap-1.5 text-sky-400">
        <FiPower className="w-4 h-4 flex-shrink-0" aria-hidden />
        Disabled
      </span>
    )
  }
  if (s === 'low') {
    return (
      <span className="inline-flex items-center gap-1.5 text-amber-400">
        <span className="text-xs" aria-hidden>
          ↓
        </span>
        Low
      </span>
    )
  }
  if (s === 'off') {
    return (
      <span className="inline-flex items-center gap-1.5 text-red-400">
        <span className="text-xs font-bold" aria-hidden>
          !
        </span>
        Off
      </span>
    )
  }
  return <span className="text-gray-400">{state || '—'}</span>
}

export default function Workers({
  hash5m,
  hash60m,
  hash24h,
  workerCounts,
  workers,
  loading,
  error,
  lastUpdated,
  formatLastShare,
  formatDec,
  displayHashrateUnit = 'TH/s',
  user = null,
}) {
  const [connectWorkersOpen, setConnectWorkersOpen] = useState(false)
  const [selected, setSelected] = useState(() => new Set())
  const [page, setPage] = useState(1)
  const perPage = 15

  const rows = useMemo(() => workers || [], [workers])
  const total = rows.length
  const pageCount = Math.max(1, Math.ceil(total / perPage))

  useEffect(() => {
    setPage((p) => Math.min(p, pageCount))
  }, [pageCount])

  const safePage = Math.min(page, pageCount)
  const sliceStart = (safePage - 1) * perPage
  const pageRows = rows.slice(sliceStart, sliceStart + perPage)

  const toggleRow = (id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllOnPage = () => {
    const ids = pageRows.map((r) => r.id)
    const allOn = ids.every((id) => selected.has(id))
    setSelected((prev) => {
      const next = new Set(prev)
      if (allOn) ids.forEach((id) => next.delete(id))
      else ids.forEach((id) => next.add(id))
      return next
    })
  }

  const lastShareText = formatLastShare?.(workerCounts?.lastShare) || '—'

  return (
    <div className="bg-gray-900/70 border border-gray-800 rounded-xl shadow-lg p-4 sm:p-6 space-y-6">
      {/* Header */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <h1 className="text-xl sm:text-2xl font-semibold text-white">Workers</h1>
        <a
          href="https://satoshiware.org/"
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-xs sm:text-sm text-violet-400 hover:text-violet-300 max-w-md"
        >
          <FiZap className="w-4 h-4 flex-shrink-0" aria-hidden />
          Boost Hashrate and Efficiency with Satoshiware
        </a>
      </div>

      {error && (
        <div className="text-xs sm:text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {/* Summary cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">5 minute Hashrate</div>
          <div className="text-2xl sm:text-3xl font-semibold text-white">
            {formatDec ? formatDec(hash5m, 3) : Number(hash5m || 0).toFixed(3)}{' '}
            <span className="text-base text-gray-400 font-normal">{displayHashrateUnit}</span>
          </div>
          <div className="text-xs text-gray-400">
            Last share <span className="text-gray-200">{lastShareText}</span>
          </div>
        </div>

        <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">Worker States</div>
          <div className="grid grid-cols-2 gap-2 text-xs sm:text-sm">
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Active</span>
              <span className="text-green-400 font-semibold">{workerCounts?.active ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Inactive</span>
              <span className="text-red-400 font-semibold">{workerCounts?.off ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Warning</span>
              <span className="text-amber-400 font-semibold">{workerCounts?.low ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-gray-300">Offline</span>
              <span className="text-gray-500 font-semibold">{workerCounts?.dis ?? 0}</span>
            </div>
          </div>
        </div>

        <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
          <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">Average Hashrate</div>
          <div className="flex items-baseline justify-between gap-4">
            <div>
              <div className="text-xs text-gray-400 mb-0.5">1 Hour</div>
              <div className="text-lg sm:text-xl font-semibold text-white">{formatHashrateTh(hash60m)}</div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-0.5">24 Hours</div>
              <div className="text-lg sm:text-xl font-semibold text-white">{formatHashrateTh(hash24h)}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Filter / actions bar */}
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center text-xs sm:text-sm text-gray-400">
          <span className="text-gray-500 whitespace-nowrap">Filter by</span>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-gray-600 bg-gray-800 px-2 py-1.5 text-gray-200 hover:bg-gray-700"
          >
            State
            <FiChevronDown className="w-3.5 h-3.5 text-gray-500" />
          </button>
          <button
            type="button"
            className="inline-flex items-center gap-1 rounded-md border border-gray-600 bg-gray-800 px-2 py-1.5 text-gray-200 hover:bg-gray-700"
          >
            Label
            <FiChevronDown className="w-3.5 h-3.5 text-gray-500" />
          </button>
          <input
            type="text"
            placeholder="Worker Attribute"
            className="min-w-[140px] flex-1 rounded-md border border-gray-600 bg-gray-800 px-2 py-1.5 text-gray-200 placeholder-gray-500 outline-none focus:border-violet-500/60 sm:max-w-xs"
          />
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            className="rounded-md border border-gray-600 bg-gray-800 p-2 text-gray-300 hover:bg-gray-700"
            aria-label="Search"
          >
            <FiSearch className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="rounded-md border border-gray-600 bg-gray-800 p-2 text-gray-300 hover:bg-gray-700"
            aria-label="Column visibility"
          >
            <FiEye className="w-4 h-4" />
          </button>
          <button
            type="button"
            className="rounded-md border border-gray-600 bg-gray-800 p-2 text-gray-300 hover:bg-gray-700"
            aria-label="Refresh"
          >
            <FiRefreshCw className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setConnectWorkersOpen(true)}
            className="rounded-md bg-violet-600 px-3 py-2 text-sm font-medium text-white hover:bg-violet-500"
          >
            Connect Workers +
          </button>
        </div>
      </div>

      <ConnectWorkers open={connectWorkersOpen} onClose={() => setConnectWorkersOpen(false)} user={user} />

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-gray-700 scrollbar-dark">
        <table className="w-full min-w-[720px] text-left text-xs sm:text-sm">
          <thead>
            <tr className="border-b border-gray-700 bg-gray-800/90 text-gray-400">
              <th className="w-10 px-2 py-3">
                <input
                  type="checkbox"
                  className="rounded border-gray-600 bg-gray-900"
                  checked={pageRows.length > 0 && pageRows.every((r) => selected.has(r.id))}
                  onChange={toggleAllOnPage}
                  aria-label="Select all on page"
                />
              </th>
              <th className="px-2 py-3 font-semibold text-gray-300">
                <span className="inline-flex items-center gap-1">
                  Worker Name
                  <FiChevronDown className="w-3.5 h-3.5 text-gray-500" aria-hidden />
                </span>
              </th>
              <th className="px-2 py-3 font-semibold text-gray-300">State</th>
              <th className="px-2 py-3 font-semibold text-gray-300">HR (5 minute)</th>
              <th className="px-2 py-3 font-semibold text-gray-300">HR (1 hour)</th>
              <th className="px-2 py-3 font-semibold text-gray-300">HR (1 day)</th>
              <th className="px-2 py-3 font-semibold text-gray-300">Alert Limit</th>
              <th className="px-2 py-3 font-semibold text-gray-300">Labels</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-800 text-gray-200">
            {loading ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-gray-500">
                  Loading workers…
                </td>
              </tr>
            ) : pageRows.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-3 py-8 text-center text-gray-500">
                  No workers found.
                </td>
              </tr>
            ) : (
              pageRows.map((w) => (
                <tr key={w.id} className="hover:bg-gray-800/40">
                  <td className="px-2 py-2.5 align-middle">
                    <input
                      type="checkbox"
                      className="rounded border-gray-600 bg-gray-900"
                      checked={selected.has(w.id)}
                      onChange={() => toggleRow(w.id)}
                      aria-label={`Select ${w.name}`}
                    />
                  </td>
                  <td className="px-2 py-2.5">
                    <button type="button" className="text-violet-400 hover:text-violet-300 hover:underline text-left">
                      {w.name}
                    </button>
                  </td>
                  <td className="px-2 py-2.5">
                    <StateCell state={w.state} />
                  </td>
                  <td className="px-2 py-2.5 font-mono tabular-nums text-gray-300">{formatHashrateTh(w.hr5m)}</td>
                  <td className="px-2 py-2.5 font-mono tabular-nums text-gray-300">{formatHashrateTh(w.hr60m)}</td>
                  <td className="px-2 py-2.5 font-mono tabular-nums text-gray-300">{formatHashrateTh(w.hr24h)}</td>
                  <td className="px-2 py-2.5 font-mono tabular-nums text-gray-300">{formatAlertLimit(w.alertLimit)}</td>
                  <td className="px-2 py-2.5 text-gray-500">{w.labels || '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {/* Footer */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between text-xs text-gray-400">
        <div className="flex flex-wrap items-center gap-3">
          <span>Items per page:</span>
          <span className="inline-flex items-center gap-1 rounded border border-gray-600 bg-gray-800 px-2 py-1 text-gray-200">
            {perPage}
            <FiChevronDown className="w-3 h-3 text-gray-500" />
          </span>
          <span className="text-gray-500">
            {total === 0 ? '0' : `${sliceStart + 1}-${Math.min(sliceStart + perPage, total)}`} of {total} items
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-gray-500">
            {safePage} of {pageCount} page{pageCount !== 1 ? 's' : ''}
          </span>
          <button
            type="button"
            disabled={safePage <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            className="rounded border border-gray-600 p-1.5 text-gray-300 hover:bg-gray-800 disabled:opacity-40"
            aria-label="Previous page"
          >
            <FiChevronLeft className="w-4 h-4" />
          </button>
          <button
            type="button"
            disabled={safePage >= pageCount}
            onClick={() => setPage((p) => Math.min(pageCount, p + 1))}
            className="rounded border border-gray-600 p-1.5 text-gray-300 hover:bg-gray-800 disabled:opacity-40"
            aria-label="Next page"
          >
            <FiChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {lastUpdated && (
        <div className="text-[11px] text-gray-600 text-right">Snapshot: {lastUpdated.toLocaleString()}</div>
      )}
    </div>
  )
}
