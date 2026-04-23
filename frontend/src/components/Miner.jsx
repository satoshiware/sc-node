import React, { useEffect, useMemo, useState } from 'react'
import { FiChevronLeft } from 'react-icons/fi'
import Workers from './Workers'
import { Bar, Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend,
} from 'chart.js'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
const WS_URL = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const COIN = 'btc'

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  BarElement,
  Tooltip,
  Legend
)

export default function Miner({ setView, user }) {
  const [showBanner, setShowBanner] = useState(true)
  const handleCloseBanner = () => {
    setShowBanner(false)
  }

  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState(null)
  const [profile, setProfile] = useState(null)
  const [poolStats, setPoolStats] = useState(null)
  const [coinUsdPrice, setCoinUsdPrice] = useState(null)
  const [workerCounts, setWorkerCounts] = useState({
    active: 0,
    low: 0,
    off: 0,
    dis: 0,
    lastShare: null,
  })
  const [dailyRewards, setDailyRewards] = useState(null)
  const [recentSeries, setRecentSeries] = useState([])
  const [workersList, setWorkersList] = useState([])
  const [minerTab, setMinerTab] = useState('mining') // 'mining' | 'workers'

  const coinKey = COIN.toLowerCase()
  const coinLabel = COIN.toUpperCase()
  const coinGeckoId = coinKey === 'btc' ? 'bitcoin' : null

  const formatDec = (value, digits = 3) => {
    const n = Number(value)
    if (!Number.isFinite(n)) return '0'
    return n.toLocaleString(undefined, { maximumFractionDigits: digits })
  }

  const toTHs = (value, unit) => {
    const n = Number(value)
    if (!Number.isFinite(n)) return 0

    const u = String(unit || '').toLowerCase()
    if (u.startsWith('eh')) return n * 1_000_000
    if (u.startsWith('ph')) return n * 1000
    if (u.startsWith('th')) return n
    if (u.startsWith('gh')) return n / 1000
    if (u.startsWith('mh')) return n / 1_000_000
    if (u.startsWith('kh')) return n / 1_000_000_000
    if (u === 'h/s' || u === 'h' || u.startsWith('hs')) return n / 1_000_000_000_000

    return n
  }

  const formatReward = (value) => {
    const n = Number(value)
    if (!Number.isFinite(n)) return `0.00000000 ${coinLabel}`
    return `${n.toFixed(8)} ${coinLabel}`
  }

  const formatLastShare = (ts) => {
    if (!ts) return '—'
    const dt = new Date(Number(ts) * 1000)
    if (Number.isNaN(dt.getTime())) return '—'
    return dt.toLocaleString()
  }

  useEffect(() => {
    if (!user?.token) {
      setLoading(false)
      setError('Missing auth token. Please sign in again.')
      return
    }

    let cancelled = false

    const fetchJson = async (endpoint) => {
      const res = await fetch(`${API_URL}${endpoint}`, {
        headers: {
          Authorization: `Bearer ${user.token}`,
        },
      })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || `Failed request: ${endpoint}`)
      }
      return res.json()
    }

    const fetchMinerJson = async (newEndpoint, legacyEndpoint) => {
      try {
        return await fetchJson(newEndpoint)
      } catch (e) {
        if (String(e?.message || '').includes('404') && legacyEndpoint) {
          return fetchJson(legacyEndpoint)
        }
        throw e
      }
    }

    const fetchUsdRate = async () => {
      if (!coinGeckoId) return null
      const res = await fetch(
        `https://api.coingecko.com/api/v3/simple/price?ids=${coinGeckoId}&vs_currencies=usd`
      )
      if (!res.ok) return null
      const data = await res.json().catch(() => null)
      const usd = Number(data?.[coinGeckoId]?.usd)
      return Number.isFinite(usd) ? usd : null
    }

    const applyMinerPayload = (profileRes, workersRes, statsRes, rewardsRes, usdRate) => {
      const profileData = profileRes?.[coinKey] || profileRes?.[coinLabel] || null
      const statsData = statsRes?.[coinKey] || statsRes?.[coinLabel] || null
      const workersMap = workersRes?.[coinKey]?.workers || workersRes?.[coinLabel]?.workers || {}
      const rewardRows = rewardsRes?.[coinKey]?.daily_rewards || rewardsRes?.[coinLabel]?.daily_rewards || []

        let maxLastShare = null
        let active = 0
        let low = 0
        let off = 0
        let dis = 0

        const unitForWorkers = profileData?.hash_rate_unit || 'Gh/s'

      Object.values(workersMap).forEach((w) => {
        const state = String(w?.state || '').toLowerCase()
        if (state === 'ok') active += 1
        else if (state === 'low') low += 1
        else if (state === 'off') off += 1
        else if (state === 'dis') dis += 1

          const share = Number(w?.last_share)
          if (Number.isFinite(share) && (!maxLastShare || share > maxLastShare)) {
            maxLastShare = share
          }
        })

        const workerRows = Object.entries(workersMap).map(([wid, w]) => {
          const u = w?.hash_rate_unit || unitForWorkers
          return {
            id: wid,
            name: w?.name || w?.worker_name || w?.worker || wid || '[auto]',
            state: String(w?.state || '').toLowerCase(),
            hr5m: toTHs(Number(w?.hash_rate_5m ?? w?.hashrate_5m ?? 0), u),
            hr60m: toTHs(Number(w?.hash_rate_60m ?? w?.hashrate_60m ?? 0), u),
            hr24h: toTHs(Number(w?.hash_rate_24h ?? w?.hashrate_24h ?? 0), u),
            alertLimit: toTHs(
              Number(w?.hash_rate_alert_limit ?? w?.alert_limit ?? w?.warning_hashrate ?? 0),
              u
            ),
            labels: Array.isArray(w?.labels) ? w.labels.join(', ') : w?.label || '',
          }
        })

      setWorkersList(workerRows)

      const normalizedRewards = rewardRows
        .map((r) => {
          const ts = Number(r?.date)
          const dt = Number.isFinite(ts) ? new Date(ts * 1000) : null
          const dayLabel = dt
            ? `${String(dt.getUTCDate()).padStart(2, '0')}.${String(dt.getUTCMonth() + 1).padStart(2, '0')}`
            : '—'

          return {
            date: ts,
            dayLabel,
            mining: Number(r?.mining_reward || 0),
            total: Number(r?.total_reward || 0),
          }
        })
        .sort((a, b) => a.date - b.date)

      setProfile(profileData)
      setPoolStats(statsData)
      if (Number.isFinite(usdRate)) {
        setCoinUsdPrice(usdRate)
      }
      setWorkerCounts({ active, low, off, dis, lastShare: maxLastShare })
      setDailyRewards(normalizedRewards)
      setLastUpdated(new Date())

      const sampleHashrateUnit = profileData?.hash_rate_unit || 'h/s'
      const sampleHash5m = toTHs(profileData?.hash_rate_5m || 0, sampleHashrateUnit)
      const sample = {
        ts: Date.now(),
        hashrate: sampleHash5m,
        activeWorkers: active,
      }
      setRecentSeries((prev) => {
        const next = [...prev, sample]
        if (next.length > 40) {
          return next.slice(next.length - 40)
        }
        return next
      })
    }

    const load = async () => {
      try {
        setError('')
        const to = new Date()
        const from = new Date(to.getTime() - 29 * 24 * 60 * 60 * 1000)
        const fromIso = from.toISOString().slice(0, 10)
        const toIso = to.toISOString().slice(0, 10)

        const [profileRes, workersRes, statsRes, rewardsRes, usdRate] = await Promise.all([
          fetchMinerJson(`/api/miner/profile?coin=${coinKey}`, `/api/miner/braiins/profile?coin=${coinKey}`),
          fetchMinerJson(`/api/miner/workers?coin=${coinKey}`, `/api/miner/braiins/workers?coin=${coinKey}`),
          fetchMinerJson(`/api/miner/stats?coin=${coinKey}`, `/api/miner/braiins/stats?coin=${coinKey}`),
          fetchMinerJson(
            `/api/miner/rewards?coin=${coinKey}&from=${fromIso}&to=${toIso}`,
            `/api/miner/braiins/rewards?coin=${coinKey}&from=${fromIso}&to=${toIso}`
          ),
          fetchUsdRate(),
        ])

        if (cancelled) return
        applyMinerPayload(profileRes, workersRes, statsRes, rewardsRes, usdRate)
      } catch (e) {
        if (!cancelled) {
          setError(e?.message || 'Failed to load miner data')
          setWorkersList([])
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    let ws
    let reconnectTimer
    let wsFailureCount = 0
    let wsConnectedOnce = false
    const connectMinerWebSocket = () => {
      if (wsFailureCount >= 3) {
        return
      }

      const url = `${WS_URL}/ws/miner?coin=${encodeURIComponent(coinKey)}&token=${encodeURIComponent(user.token)}`
      ws = new WebSocket(url)

      ws.onopen = () => {
        wsFailureCount = 0
        wsConnectedOnce = true
      }

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data)
          if (msg?.type === 'miner_update') {
            applyMinerPayload(msg.profile, msg.workers, msg.stats, msg.rewards, null)
            if (msg.updated_at) {
              const dt = new Date(msg.updated_at)
              if (!Number.isNaN(dt.getTime())) {
                setLastUpdated(dt)
              }
            }
          } else if (msg?.type === 'error') {
            setError(msg.detail || 'Miner websocket error')
          }
        } catch {
          // Ignore malformed websocket payloads and keep stream alive.
        }
      }

      ws.onerror = () => {
        wsFailureCount += 1
      }

      ws.onclose = () => {
        if (!cancelled) {
          if (!wsConnectedOnce) {
            wsFailureCount += 1
          }
          if (wsFailureCount >= 3) {
            setError((prev) => prev || 'Live miner updates unavailable; using periodic refresh.')
            return
          }
          reconnectTimer = setTimeout(connectMinerWebSocket, 2000)
        }
      }
    }

    setLoading(true)
    load()
    connectMinerWebSocket()
    const interval = setInterval(load, 30000)

    return () => {
      cancelled = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      if (ws) ws.close()
      clearInterval(interval)
    }
  }, [coinGeckoId, coinKey, coinLabel, user?.token])

  const hashrateUnit = profile?.hash_rate_unit || 'Gh/s'
  const displayHashrateUnit = 'TH/s'
  const hash5m = toTHs(profile?.hash_rate_5m || 0, hashrateUnit)
  const hash60m = toTHs(profile?.hash_rate_60m || 0, hashrateUnit)
  const hash24h = toTHs(profile?.hash_rate_24h || 0, hashrateUnit)
  const todayReward = Number(profile?.today_reward || 0)
  const todayRewardUsd = Number.isFinite(coinUsdPrice) ? todayReward * coinUsdPrice : null
  const allTimeReward = Number(profile?.all_time_reward || 0)
  const currentBalance = Number(profile?.current_balance || 0)
  const yesterdayTotalReward = dailyRewards?.length > 1 ? dailyRewards[dailyRewards.length - 2]?.total || 0 : 0

  const recentChartSamples = useMemo(() => {
    if (!recentSeries.length) {
      return [
        {
          ts: Date.now(),
          hashrate: hash5m,
          activeWorkers: workerCounts.active,
        },
      ]
    }
    return recentSeries.slice(-12)
  }, [hash5m, recentSeries, workerCounts.active])

  const labels = recentChartSamples.map((p) =>
    new Date(p.ts).toLocaleTimeString([], { minute: '2-digit', second: '2-digit' })
  )
  const hashrateValues = recentChartSamples.map((p) => p.hashrate)
  const workerValues = recentChartSamples.map((p) => p.activeWorkers)

  const recentHashrateData = {
    labels,
    datasets: [
      {
        label: '5 min Hashrate',
        data: hashrateValues,
        borderColor: '#6366F1', // indigo-500
        backgroundColor: 'rgba(129,140,248,0.18)', // indigo-400 with alpha
        tension: 0.25,
        fill: true,
        pointRadius: 0,
        borderWidth: 2,
        yAxisID: 'y',
      },
      {
        label: 'Active workers',
        data: workerValues,
        borderColor: '#10B981', // emerald-500
        backgroundColor: 'rgba(16,185,129,0.12)', // emerald-400 with alpha
        tension: 0.15,
        fill: false,
        pointRadius: 0,
        borderWidth: 1.5,
        yAxisID: 'y1',
      },
    ],
  }

  const recentHashrateOptions = {
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: 'index', intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label(context) {
            const label = context.dataset.label || ''
            const value = context.parsed.y
            if (label.includes('Hashrate')) {
              return `${label}: ${Number(value).toFixed(3)} ${displayHashrateUnit}`
            }
            return `${label}: ${value}`
          },
        },
      },
    },
    scales: {
      x: {
        ticks: { color: '#9CA3AF', maxTicksLimit: 9 },
        grid: { color: 'rgba(156,163,175,0.15)' },
      },
      y: {
        type: 'linear',
        position: 'left',
        ticks: {
          color: '#9CA3AF',
          callback: (v) => `${Number(v).toFixed(2)} ${displayHashrateUnit}`,
        },
        grid: { color: 'rgba(156,163,175,0.12)' },
      },
      y1: {
        type: 'linear',
        position: 'right',
        ticks: {
          color: '#9CA3AF',
          stepSize: 1,
          precision: 0,
        },
        grid: { drawOnChartArea: false },
      },
    },
  }

  const dailyRewardsChartData = useMemo(() => {
    if (!dailyRewards || dailyRewards.length === 0) return null
    return {
      labels: dailyRewards.map((d) => d.dayLabel),
      datasets: [
        {
          label: 'Mining Reward',
          data: dailyRewards.map((d) => d.mining),
          backgroundColor: 'rgba(99,102,241,0.85)', // indigo-500
          borderWidth: 0,
          // Narrower bars (smaller than the default bar width in the category).
          barPercentage: 0.55,
          categoryPercentage: 0.85,
          maxBarThickness: 12,
        },
      ],
    }
  }, [dailyRewards])

  const dailyRewardsChartOptions = useMemo(
    () => ({
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: 'bottom',
          labels: {
            boxWidth: 10,
            boxHeight: 10,
            usePointStyle: true,
          },
        },
        tooltip: {
          callbacks: {
            label(context) {
              const label = context.dataset.label || ''
              const v = Number(context.parsed.y) || 0
              return `${label}: ${v.toFixed(8)} ${coinLabel}`
            },
          },
        },
      },
      scales: {
        x: {
          ticks: {
            color: '#9CA3AF',
            maxTicksLimit: 6,
          },
          grid: { display: false },
          // Draw the bottom axis border to match the reference UI.
          border: {
            display: true,
            color: 'rgba(156,163,175,0.55)',
            width: 1,
          },
        },
        y: {
          ticks: {
            color: '#9CA3AF',
            callback: (v) => `${Number(v).toFixed(8)} ${coinLabel}`,
          },
          grid: { color: 'rgba(156,163,175,0.15)' },
          // Draw the left axis border to match the reference UI.
          border: {
            display: true,
            color: 'rgba(156,163,175,0.55)',
            width: 1,
          },
        },
      },
    }),
    []
  )

  return (
    <div className="min-h-screen p-2 sm:p-4">
      <div className="max-w-6xl mx-auto">
        {/* Back bar */}
        <div className="sticky top-0 z-30 bg-gray-900/60 backdrop-blur-sm px-3 py-2 rounded-b-md mb-4 flex items-center">
          <button
            type="button"
            onClick={() => setView && setView('home')}
            className="text-sm text-gray-200 hover:text-white flex items-center gap-2"
          >
            <FiChevronLeft className="w-4 h-4" />
            Back
          </button>
        </div>

        <div className="mt-2 space-y-4">
          {/* Top sub-navigation */}
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 text-xs sm:text-sm">
              <button
                type="button"
                onClick={() => setMinerTab('mining')}
                className={
                  minerTab === 'mining'
                    ? 'px-3 py-1.5 rounded-full bg-blue-600 text-white font-medium shadow-sm'
                    : 'px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700'
                }
              >
                Mining
              </button>
              <button
                type="button"
                onClick={() => setMinerTab('workers')}
                className={
                  minerTab === 'workers'
                    ? 'px-3 py-1.5 rounded-full bg-blue-600 text-white font-medium shadow-sm'
                    : 'px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700'
                }
              >
                Workers
              </button>
              <button
                type="button"
                className="px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700 opacity-80 cursor-not-allowed"
                disabled
              >
                History
              </button>
            </div>
          </div>

          {/* Info banner */}
          {showBanner && minerTab === 'mining' && (
            <div className="relative bg-amber-500/10 border border-amber-500/40 rounded-lg px-4 py-3 pr-10 text-xs sm:text-sm text-amber-100">
              <button
                type="button"
                onClick={handleCloseBanner}
                className="absolute top-2 right-2 text-amber-200/80 hover:text-amber-100 hover:bg-amber-500/20 rounded-full w-6 h-6 flex items-center justify-center text-xs"
                aria-label="Close banner"
              >
                ×
              </button>
              <div className="font-medium mb-1">Don't sell, borrow</div>
              <p className="text-amber-100/80">
                Get stable coins or fiat against your AZCoins. Instant liquidity with low fees. This is a demo banner for miner information.
              </p>
            </div>
          )}

          {minerTab === 'workers' ? (
            <Workers
              hash5m={hash5m}
              hash60m={hash60m}
              hash24h={hash24h}
              workerCounts={workerCounts}
              workers={workersList}
              loading={loading}
              error={error}
              lastUpdated={lastUpdated}
              formatLastShare={formatLastShare}
              formatDec={formatDec}
              displayHashrateUnit={displayHashrateUnit}
              user={user}
            />
          ) : (
          <div className="bg-gray-900/70 border border-gray-800 rounded-xl shadow-lg p-4 sm:p-6 space-y-6">
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h1 className="text-xl sm:text-2xl font-semibold text-white">Dashboard</h1>
              <div className="text-xs sm:text-sm text-gray-400">
                Last updated{' '}
                <span className="text-gray-200">{lastUpdated ? lastUpdated.toLocaleTimeString() : '—'}</span>
              </div>
            </div>

            {error && (
              <div className="text-xs sm:text-sm text-red-300 bg-red-500/10 border border-red-500/30 rounded-md px-3 py-2">
                {error}
              </div>
            )}

            {/* Top stats row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* 5 minute hashrate */}
              <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  5 minute Hashrate
                </div>
                <div className="text-2xl sm:text-3xl font-semibold text-white">
                  {formatDec(hash5m, 3)} <span className="text-base text-gray-400 font-normal">{displayHashrateUnit}</span>
                </div>
                <div className="text-xs text-gray-400">
                  Last share <span className="text-gray-200">{formatLastShare(workerCounts.lastShare)}</span>
                </div>
              </div>

              {/* Worker states */}
              <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Worker States
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs sm:text-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Active</span>
                    <span className="text-green-400 font-semibold">{workerCounts.active}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Inactive</span>
                    <span className="text-red-400 font-semibold">{workerCounts.off}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Warning</span>
                    <span className="text-amber-400 font-semibold">{workerCounts.low}</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Offline</span>
                    <span className="text-gray-500 font-semibold">{workerCounts.dis}</span>
                  </div>
                </div>
              </div>

              {/* Best diff / blocks found */}
              <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Mining Stats
                </div>
                <div className="flex items-baseline justify-between gap-4">
                  <div>
                    <div className="text-xs text-gray-400 mb-0.5">best_diff (Highest Share Difficulty)</div>
                    <div className="text-lg sm:text-xl font-semibold text-white">
                      {formatDec(4812121.210808747, 6)}
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400 mb-0.5">blocks_found</div>
                    <div className="text-lg sm:text-xl font-semibold text-white">0</div>
                  </div>
                </div>
              </div>
            </div>

            {/* Recent hashrate chart */}
            <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 sm:p-5 space-y-3">
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs sm:text-sm">
                <div className="font-medium text-gray-200">Recent Hashrate</div>
                <div className="flex items-center gap-3 text-gray-400">
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-indigo-400" />
                    <span className="hidden sm:inline">5 min Hashrate</span>
                  </span>
                  <span className="inline-flex items-center gap-1">
                    <span className="w-2 h-2 rounded-sm bg-emerald-400" />
                    <span className="hidden sm:inline">Active workers</span>
                  </span>
                </div>
              </div>
              <div className="h-48 sm:h-56 md:h-64 rounded-md bg-gradient-to-b from-gray-900/40 via-gray-900/80 to-gray-950 border border-gray-700 px-2 py-1">
                <Line data={recentHashrateData} options={recentHashrateOptions} />
              </div>
            </div>

            {/* Rewards section */}
            <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 sm:p-5 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <h2 className="text-sm sm:text-base font-semibold text-white">Rewards</h2>
                <button className="text-xs sm:text-sm text-blue-400 hover:text-blue-300">
                  Rewards history
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs sm:text-sm">
                <div>
                  <div className="text-gray-400 mb-1">Today's Mining Rewards</div>
                  <div className="text-lg font-semibold text-white">{formatReward(todayReward)}</div>
                  <div className="text-gray-500 text-xs">
                    {todayRewardUsd === null
                      ? '≈ — USD'
                      : `≈ ${todayRewardUsd.toLocaleString(undefined, {
                          style: 'currency',
                          currency: 'USD',
                          minimumFractionDigits: 2,
                          maximumFractionDigits: 2,
                        })} USD`}
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Yesterday's Total Reward</div>
                  <div className="text-lg font-semibold text-white">{formatReward(yesterdayTotalReward)}</div>
                  <div className="text-gray-500 text-xs">Updated from local pool daily rewards</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">All Time Reward</div>
                  <div className="text-lg font-semibold text-white">{formatReward(allTimeReward)}</div>
                  <div className="text-gray-500 text-xs">Reward scheme: FPPS (fee 2.5%)</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Next Payout ETA</div>
                  <div className="text-lg font-semibold text-white">—</div>
                  <div className="text-gray-500 text-xs">Account balance: {formatReward(currentBalance)}</div>
                </div>
              </div>

              {loading ? (
                <div className="mt-2 text-xs sm:text-sm text-gray-400 bg-gray-900/60 border border-dashed border-gray-700 rounded-md px-3 py-3">
                  Loading rewards…
                </div>
              ) : !dailyRewards || dailyRewards.length === 0 ? (
                <div className="mt-2 text-xs sm:text-sm text-gray-400 bg-gray-900/60 border border-dashed border-gray-700 rounded-md px-3 py-3">
                  You have no daily rewards yet. Your rewards for each day will appear here once confirmed and finalized.
                </div>
              ) : (
                <div className="mt-2">
                  <div className="flex items-center justify-between gap-2 mb-2 text-xs sm:text-sm text-gray-400">
                    <div className="inline-flex items-center gap-2">
                      Rewards In last 30 days
                      <span className="inline-flex w-4 h-4 items-center justify-center rounded-full border border-gray-600 text-[10px] text-gray-500">
                        i
                      </span>
                    </div>
                    <button className="text-xs text-blue-400 hover:text-blue-300">
                      Rewards history
                    </button>
                  </div>
                  <div className="h-48 sm:h-56 rounded-md bg-white/5 border border-gray-700 px-2 py-1">
                    <Bar data={dailyRewardsChartData} options={dailyRewardsChartOptions} />
                  </div>
                </div>
              )}
            </div>

            {/* Pool statistics */}
            <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 sm:p-5">
              <div className="flex flex-wrap items-center justify-between gap-2 mb-4">
                <h2 className="text-sm sm:text-base font-semibold text-white">Pool Statistics</h2>
                <button className="text-xs sm:text-sm text-blue-400 hover:text-blue-300">
                  Detailed statistics
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs sm:text-sm">
                <div>
                  <div className="text-gray-400 mb-1">Pool Effective HR (30m avg)</div>
                  <div className="text-lg font-semibold text-white">
                    {formatDec(toTHs(poolStats?.pool_60m_hash_rate || 0, poolStats?.hash_rate_unit || hashrateUnit), 3)}{' '}
                    {displayHashrateUnit}
                  </div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Active Users</div>
                  <div className="text-lg font-semibold text-white">{formatDec(poolStats?.pool_active_users || 0, 0)}</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Total Workers</div>
                  <div className="text-lg font-semibold text-white">{formatDec(poolStats?.pool_active_workers || 0, 0)}</div>
                </div>
              </div>
            </div>
          </div>
          )}
        </div>
      </div>
    </div>
  )
}

