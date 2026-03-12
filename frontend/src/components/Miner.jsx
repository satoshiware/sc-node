import React, { useState } from 'react'
import { FiChevronLeft } from 'react-icons/fi'
import { Line } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
} from 'chart.js'

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Tooltip, Legend)

export default function Miner({ setView }) {
  const [showBanner, setShowBanner] = useState(true)

  const handleCloseBanner = () => {
    setShowBanner(false)
  }

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
                  <div className="text-lg font-semibold text-white">0.00000007 BTC</div>
                  <div className="text-gray-500 text-xs">≈ $0.00 USD</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Yesterday's Total Reward</div>
                  <div className="text-lg font-semibold text-white">0.00000000 BTC</div>
                  <div className="text-gray-500 text-xs">Est. Profitability: 0.00000034 BTC</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">All Time Reward</div>
                  <div className="text-lg font-semibold text-white">0.00000000 BTC</div>
                  <div className="text-gray-500 text-xs">Reward scheme: FPPS (fee 2.5%)</div>
                </div>
                <div>
                  <div className="text-gray-400 mb-1">Next Payout ETA</div>
                  <div className="text-lg font-semibold text-white">—</div>
                  <div className="text-gray-500 text-xs">Account balance: 0.00000000 BTC</div>
                </div>
              </div>

              <div className="mt-2 text-xs sm:text-sm text-gray-400 bg-gray-900/60 border border-dashed border-gray-700 rounded-md px-3 py-3">
                You have no daily rewards yet. Your rewards for each day will appear here once confirmed and finalized.
              </div>
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

