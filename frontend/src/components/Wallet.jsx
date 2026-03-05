import React, { useState } from 'react'
import { FiChevronLeft } from 'react-icons/fi'
import Profile from './Profile'
import Deposit from './Deposite'
import ManageFunds from './ManageFunds'

export default function Wallet({ setView, user, onSignOut }){
  const [assets] = useState([
    { id: 'BTC', name: 'BTC-SATS', total: '0.01234567', limits: '—', available: '0.01000000', history: [
      { date: '2026-02-01', time: '12:12:12', dir: 'in', amount: '0.00500000' },
      { date: '2026-01-20', time: '09:05:34', dir: 'out', amount: '0.00200000' },
    ]},
    { id: 'AZC', name: 'AZC-SATS', total: '1.76543210', limits: '—', available: '1.76543210', history: [
      { date: '2026-01-25', time: '16:29:24', dir: 'in', amount: '0.50000000' },
    ]},
    { id: 'USD', name: 'USD-SATS', total: '100.00', limits: '—', available: '100.00', history: []},

    
  ])

  const [selected, setSelected] = useState(null)

  const handleDeposit = (a) => { alert(`Deposit for ${a.name}`) }
  const handleWithdraw = (a) => { alert(`Withdraw for ${a.name}`) }

  return (
    <div className="min-h-screen p-2 sm:p-4">
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

      <div className="space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Portfolio</h2>
            <div className="text-sm text-gray-400">Wallet & balances</div>
          </div>
          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <Deposit />
            <ManageFunds />
            <Profile user={user} onSignOut={onSignOut} />
          </div>
        </div>

        <div className="bg-gray-800 p-3 sm:p-4 rounded-md min-w-0">
          <div className="mb-4">
            <div className="text-sm text-gray-400">Bitcoin (Satoshis)</div>
            <div className="text-xl sm:text-2xl font-semibold text-gray-100">8,485,976 sats</div>
          </div>

          <div className="overflow-x-auto -mx-1 px-1">
            <div className="grid grid-cols-4 md:grid-cols-6 gap-2 text-xs text-gray-400 border-b border-gray-700 pb-2 min-w-[400px] md:min-w-0">
              <div>Asset</div>
              <div>Total</div>
              <div className="hidden md:block">Limits</div>
              <div>Available</div>
              <div className="col-span-2 md:col-span-1 text-right">Actions</div>
              <div className="hidden md:block" />
            </div>

            <div className="mt-2 space-y-2">
              {assets.map(a => (
                <div key={a.id} className="grid grid-cols-4 md:grid-cols-6 gap-2 items-center text-sm text-gray-200 bg-gray-900/20 p-2 rounded min-w-[400px] md:min-w-0">
                  <div className="min-w-0">
                    <button type="button" onClick={() => setSelected(a)} className="text-left hover:underline truncate block w-full">{a.name}</button>
                  </div>
                  <div className="truncate">{a.total}</div>
                  <div className="hidden md:block truncate">{a.limits}</div>
                  <div className="truncate">{a.available}</div>
                  <div className="flex gap-2 col-span-2 md:col-span-1">
                    <button onClick={() => handleDeposit(a)} className="bg-blue-600 text-white px-2 py-1 rounded text-xs whitespace-nowrap">Deposit</button>
                    <button onClick={() => handleWithdraw(a)} className="bg-gray-700 text-gray-200 px-2 py-1 rounded text-xs whitespace-nowrap">Withdraw</button>
                  </div>
                  <div className="hidden md:block text-right text-xs text-gray-400">{a.history.length} transfers</div>
                </div>
              ))}
            </div>
          </div>

          {selected && (
            <div className="mt-4 bg-gray-900 p-3 rounded">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="text-sm font-semibold text-gray-100">Transfer history — {selected.name}</div>
                <button onClick={() => setSelected(null)} className="text-xs text-gray-400">Close</button>
              </div>

              <div className="mt-3 text-sm text-gray-300">
                {selected.history.length === 0 ? (
                  <div className="text-gray-500">No transfers</div>
                ) : (
                  <div className="space-y-2">
                    {selected.history.map((h, i) => (
                      <div key={i} className="flex flex-wrap items-center justify-between gap-2 border-b border-gray-800 pb-2">
                        <div className="text-xs text-gray-400">{h.date} {h.time}</div>
                        <div className={`text-sm ${h.dir === 'in' ? 'text-green-300' : 'text-red-300'}`}>{h.dir.toUpperCase()}</div>
                        <div className="text-sm">{h.amount}</div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
