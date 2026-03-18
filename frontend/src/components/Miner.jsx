import React, { useEffect, useMemo, useState } from 'react'
import { FiChevronLeft } from 'react-icons/fi'
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

  const [dailyRewards, setDailyRewards] = useState(null) // null=loading, []=no rewards, array=has rewards

  // Mock daily rewards (AZC) shaped for the rewards bar chart.
  // In a real setup, this should be fetched from the backend per account.
  const mockDailyRewards = useMemo(() => {
    const start = new Date('2026-02-16T00:00:00Z')
    const out = []
    for (let i = 0; i < 30; i++) {
      const d = new Date(start.getTime() + i * 86400000)
      const dayLabel = `${String(d.getUTCDate()).padStart(2, '0')}.${String(
        d.getUTCMonth() + 1
      ).padStart(2, '0')}`

      // Make last ~6 days higher, matching your screenshot look.
      const isLate = i >= 24
      const isVeryLate = i >= 28

      const mining = isLate
        ? isVeryLate
          ? 0.00000014 + (i - 28) * 0.00000001
          : 0.00000011 + (i - 24) * 0.00000001
        : 0.00000002 + i * 0.000000001

      out.push({
        dayLabel,
        mining,
      })
    }
    return out
  }, [])

  // Show message for "new to account" users, then show chart if they already visited before.
  useEffect(() => {
    const key = user?.id != null ? `miner_daily_rewards_seen_${user.id}` : 'miner_daily_rewards_seen_guest'
    const seen = localStorage.getItem(key)
    if (seen) {
      setDailyRewards(mockDailyRewards)
      return
    }
    setDailyRewards([])
    localStorage.setItem(key, '1')
  }, [mockDailyRewards, user?.id])

  // Mock data for recent hashrate and active workers
  const labels = ['18:00', '18:10', '18:20', '18:30', '18:40', '18:50', '19:00', '19:10', '19:20']
  const hashrateValues = [0, 0, 0, 0, 0, 4.2, 5.1, 4.8, 5.0] // TH/s
  const workerValues = [0, 0, 0, 0, 0, 1, 1, 1, 1] // count

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
              return `${label}: ${value.toFixed(3)} TH/s`
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
          callback: (v) => `${v}T`,
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
              return `${label}: ${v.toFixed(8)} AZC`
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
            callback: (v) => `${Number(v).toFixed(8)} AZC`,
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
              <button className="px-3 py-1.5 rounded-full bg-blue-600 text-white font-medium shadow-sm">
                Mining
              </button>
              <button className="px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700">
                Funds
              </button>
              <button className="px-3 py-1.5 rounded-full bg-gray-800 text-gray-300 border border-gray-700 hover:bg-gray-700">
                History
              </button>
            </div>
          </div>

          {/* Info banner */}
          {showBanner && (
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

          {/* Main dashboard card */}
          <div className="bg-gray-900/70 border border-gray-800 rounded-xl shadow-lg p-4 sm:p-6 space-y-6">
            {/* Header */}
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h1 className="text-xl sm:text-2xl font-semibold text-white">Dashboard</h1>
              <div className="text-xs sm:text-sm text-gray-400">
                Last updated <span className="text-gray-200">3 minutes ago</span>
              </div>
            </div>

            {/* Top stats row */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {/* 5 minute hashrate */}
              <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  5 minute Hashrate
                </div>
                <div className="text-2xl sm:text-3xl font-semibold text-white">
                  5.043 <span className="text-base text-gray-400 font-normal">TH/s</span>
                </div>
                <div className="text-xs text-gray-400">
                  Last share <span className="text-gray-200">3 minutes ago</span>
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
                    <span className="text-green-400 font-semibold">1</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Inactive</span>
                    <span className="text-red-400 font-semibold">0</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Warning</span>
                    <span className="text-amber-400 font-semibold">0</span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-gray-300">Offline</span>
                    <span className="text-gray-500 font-semibold">0</span>
                  </div>
                </div>
              </div>

              {/* Average hashrate */}
              <div className="bg-gray-800/80 border border-gray-700 rounded-lg p-4 space-y-2">
                <div className="text-xs font-medium text-gray-400 uppercase tracking-wide">
                  Average Hashrate
                </div>
                <div className="flex items-baseline justify-between gap-4">
                  <div>
                    <div className="text-xs text-gray-400 mb-0.5">1 Hour</div>
                    <div className="text-lg sm:text-xl font-semibold text-white">
                      4.222 <span className="text-xs text-gray-400 font-normal">TH/s</span>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-gray-400 mb-0.5">24 Hours</div>
                    <div className="text-lg sm:text-xl font-semibold text-white">
                      175.9 <span className="text-xs text-gray-400 font-normal">GH/s</span>
                    </div>
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
                  <div className="text-lg font-semibold text-white">0.00000007 AZC</div>
                  <div className="text-gray-500 text-xs">≈ $0.00 USD</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Yesterday's Total Reward</div>
                  <div className="text-lg font-semibold text-white">0.00000000 AZC</div>
                  <div className="text-gray-500 text-xs">Est. Profitability: 0.00000034 AZC</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">All Time Reward</div>
                  <div className="text-lg font-semibold text-white">0.00000000 AZC</div>
                  <div className="text-gray-500 text-xs">Reward scheme: FPPS (fee 2.5%)</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Next Payout ETA</div>
                  <div className="text-lg font-semibold text-white">—</div>
                  <div className="text-gray-500 text-xs">Account balance: 0.00000000 AZC</div>
                </div>
              </div>

              {dailyRewards == null ? (
                <div className="mt-2 text-xs sm:text-sm text-gray-400 bg-gray-900/60 border border-dashed border-gray-700 rounded-md px-3 py-3">
                  Loading rewards…
                </div>
              ) : dailyRewards.length === 0 ? (
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
                  <div className="text-lg font-semibold text-white">13.92 EH/s</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Active Users</div>
                  <div className="text-lg font-semibold text-white">12 288</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Active Workers</div>
                  <div className="text-lg font-semibold text-white">103 909</div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

