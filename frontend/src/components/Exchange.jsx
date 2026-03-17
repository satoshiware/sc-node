import React from 'react'
import { FiChevronLeft } from 'react-icons/fi'
import MarketSelect from './MarketSelect'

export default function Exchange({ setView, user, balances }) {
  const accountNumber = user?.id ?? 14
  const fullName =
    user?.name ||
    `${user?.first_name ?? ''} ${user?.last_name ?? ''}`.trim() ||
    '—'
  const email = user?.email || user?.username || '—'
  const phone = user?.phone || '—'

  const totalSats = balances?.sats ?? 0
  const totalCoins = balances?.azc ?? 0

  // Static rows shaped to closely mirror the spreadsheet Exchange section.
  const exchangeRows = [
    {
      id: 1,
      direction: 'In',
      limitMarket: 'Limit',
      boughtSold: 'Bought',
      amountCoins: 2.0,
      priceSats: 422,
      totalSats: 422,
      feeSats: 3,
      time: '3/13/2026 9:37:47',
    },
    {
      id: 2,
      direction: 'In',
      limitMarket: 'Limit',
      boughtSold: 'Bought',
      amountCoins: 1.0,
      priceSats: 422,
      totalSats: 422,
      feeSats: 3,
      time: '3/13/2026 9:31:38',
    },
    {
      id: 3,
      direction: 'Out',
      limitMarket: 'Limit',
      boughtSold: 'Sold',
      amountCoins: 1.0,
      priceSats: 459,
      totalSats: 459,
      feeSats: 3,
      time: '3/12/2026 22:35:48',
    },
  ]

  const satsBought = exchangeRows
    .filter((r) => r.boughtSold === 'Bought')
    .reduce((sum, r) => sum + r.totalSats, 0)
  const satsSold = exchangeRows
    .filter((r) => r.boughtSold === 'Sold')
    .reduce((sum, r) => sum + r.totalSats, 0)
  const totalFees = exchangeRows.reduce((sum, r) => sum + r.feeSats, 0)
  const satsNet = satsSold - satsBought - totalFees

  const thirtyDayVol = exchangeRows.reduce(
    (sum, r) => sum + r.totalSats,
    0
  )

  return (
    <div className="min-h-screen p-2 sm:p-4">
      <div className="max-w-6xl mx-auto">
        {/* Header: back + market selector */}
        <div className="sticky top-0 z-30 bg-gray-900/70 backdrop-blur-sm px-3 py-2 rounded-b-md mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div className="flex items-center gap-3">
            <button
              type="button"
              onClick={() => setView && setView('home')}
              className="text-sm text-gray-200 hover:text-white flex items-center gap-2"
            >
              <FiChevronLeft className="w-4 h-4" />
              Back
            </button>
            {/* <MarketSelect /> */}
          </div>
          <div className="text-[11px] sm:text-xs md:text-sm text-gray-400">
            Slim&apos;s Circle P2P Exchange AZCoins / SATS
          </div>
        </div>

        {/* Page header similar to Order management */}
        <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Exchange</h2>
            <p className="mt-1 text-sm text-gray-400">
              Overview of your AZCoins / SATS exchange activity.
            </p>
          </div>
        </div>

        {/* Top summary area (account + totals) */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-4">
          {/* Account details */}
          <div className="bg-gray-800 border border-gray-700 rounded-md p-3 text-xs sm:text-sm">
            <div className="font-semibold text-gray-200 mb-2">
              Account #
            </div>
            <div className="grid grid-cols-2 gap-y-1 text-gray-300">
              <div className="text-gray-400">Account #</div>
              <div>{accountNumber}</div>
              <div className="text-gray-400">Name</div>
              <div>{fullName}</div>
              <div className="text-gray-400">Phone</div>
              <div>{phone}</div>
              <div className="text-gray-400">Email</div>
              <div className="truncate">{email}</div>
            </div>
          </div>

          {/* Balances / totals */}
          <div className="bg-gray-800 border border-gray-700 rounded-md p-3 text-xs sm:text-sm">
            <div className="font-semibold text-gray-200 mb-2">
              Balances
            </div>
            <div className="grid grid-cols-2 gap-y-1 text-gray-300">
              <div className="text-gray-400">Total (SATS)</div>
              <div className="text-emerald-400 font-semibold">
                {totalSats.toLocaleString()} SATS
              </div>
              <div className="text-gray-400">Total (Coins)</div>
              <div className="text-emerald-400 font-semibold">
                {totalCoins.toFixed(8)} Coins
              </div>
              <div className="text-gray-400">30 Day Volume</div>
              <div className="text-emerald-300 font-semibold">
                {thirtyDayVol.toLocaleString()} SATS
              </div>
            </div>
          </div>

          {/* SATS summary block */}
          <div className="bg-gray-800 border border-gray-700 rounded-md p-3 text-xs sm:text-sm">
            <div className="font-semibold text-gray-200 mb-2">
              SATS Summary
            </div>
            <div className="grid grid-cols-2 gap-y-1 text-gray-300">
              <div className="text-gray-400">Sats Earned</div>
              <div className="text-emerald-400 font-semibold">
                {satsSold.toLocaleString()} SATS
              </div>
              <div className="text-gray-400">Sats Spent</div>
              <div className="text-red-400 font-semibold">
                {satsBought.toLocaleString()} SATS
              </div>
              <div className="text-gray-400">Fees (Paid Fees)</div>
              <div className="text-amber-300 font-semibold">
                {totalFees.toLocaleString()} SATS
              </div>
              <div className="text-gray-400">Sats Net</div>
              <div
                className={
                  satsNet >= 0
                    ? 'text-emerald-400 font-semibold'
                    : 'text-red-400 font-semibold'
                }
              >
                {satsNet.toLocaleString()} SATS
              </div>
            </div>
          </div>
        </div>

        {/* Exchange table (no transfer history / no mining payouts) */}
        <div className="bg-gray-800/95 border border-gray-700 rounded-lg overflow-hidden">
          <div className="px-3 py-2 border-b border-gray-700 flex items-center justify-between">
            <div className="text-sm sm:text-base font-semibold text-gray-100">
              Exchange
            </div>
          </div>
          <div className="overflow-x-auto scrollbar-dark">
            <table className="w-full min-w-[720px] text-xs sm:text-sm border-collapse">
              <thead>
                <tr className="bg-gray-700/60 text-gray-200 border-b-2 border-gray-600">
                  <th className="px-3 py-2.5 font-semibold text-left border-r border-gray-600">
                    Direction
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-left border-r border-gray-600">
                    Limit/Market
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-left border-r border-gray-600">
                    Bought/Sold
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-right border-r border-gray-600">
                    Amount (Coins)
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-right border-r border-gray-600">
                    Price (SATS)
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-right border-r border-gray-600">
                    Total (SATS)
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-right border-r border-gray-600">
                    Fee (SATS)
                  </th>
                  <th className="px-3 py-2.5 font-semibold text-right">
                    Time
                  </th>
                </tr>
              </thead>
              <tbody className="text-gray-200">
                {exchangeRows.length === 0 ? (
                  <tr>
                    <td
                      colSpan={8}
                      className="px-3 py-10 text-center text-gray-500 border-t border-gray-700"
                    >
                      No exchange history yet.
                    </td>
                  </tr>
                ) : (
                  exchangeRows.map((r) => (
                    <tr
                      key={r.id}
                      className="border-b border-gray-700/80 hover:bg-gray-700/20"
                    >
                      <td className="px-3 py-2 border-r border-gray-700/80 text-gray-300">
                        {r.direction}
                      </td>
                      <td className="px-3 py-2 border-r border-gray-700/80 text-gray-300">
                        {r.limitMarket}
                      </td>
                      <td
                        className={`px-3 py-2 border-r border-gray-700/80 ${
                          r.boughtSold === 'Bought'
                            ? 'text-emerald-400'
                            : 'text-red-400'
                        }`}
                      >
                        {r.boughtSold}
                      </td>
                      <td className="px-3 py-2 border-r border-gray-700/80 text-right font-mono text-gray-200">
                        {r.amountCoins.toFixed(8)}
                      </td>
                      <td className="px-3 py-2 border-r border-gray-700/80 text-right">
                        {r.priceSats.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 border-r border-gray-700/80 text-right">
                        {r.totalSats.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 border-r border-gray-700/80 text-right text-gray-300">
                        {r.feeSats.toLocaleString()}
                      </td>
                      <td className="px-3 py-2 text-right text-gray-400 whitespace-nowrap">
                        {r.time}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  )
}

