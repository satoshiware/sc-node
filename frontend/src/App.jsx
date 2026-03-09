import React, { useState } from 'react'
import { FiChevronDown, FiClock } from 'react-icons/fi'
import Header from './components/Header'
import LeftChart from './components/LeftChart'
import OrderBook from './components/OrderBook'
import TradeHistory from './components/TradeHistory'
import BuyPanel from './components/BuyPanel'
import OrdersTable from './components/OrdersTable'
import OrderManagement from './components/OrderManagement'
import Wallet from './components/Wallet'
import Exchange from './components/Exchange'
import Login from './components/Login'

export default function App(){
  const [view, setView] = useState('home')
  const [priceGap, setPriceGap] = useState(1)
  const [balances, setBalances] = useState({ azc: 133.66, sats: 50000 }) // Initial balances for testing
  const [user, setUser] = useState(() => {
    const stored = localStorage.getItem('app_user')
    return stored ? JSON.parse(stored) : null
  })

  function handleLogin(userData) {
    setUser(userData)
    localStorage.setItem('app_user', JSON.stringify(userData))
  }

  function handleSignOut() {
    setUser(null)
    localStorage.removeItem('app_user')
  }

  if (!user) {
    return <Login onLogin={handleLogin} />
  }

  return (
    <div className="min-h-screen p-2 sm:p-4">
      {view === 'home' && <Header setView={setView} user={user} onSignOut={handleSignOut} />}

      {view === 'orders' ? (
        <OrderManagement setView={setView} user={user} onSignOut={handleSignOut} />
      ) : view === 'wallet' ? (
        <Wallet setView={setView} user={user} onSignOut={handleSignOut} balances={balances} />
      ) : view === 'exchange' ? (
        <Exchange setView={setView} />
      ) : (
        <div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-12 lg:gap-4 xl:gap-4">
          <div className="flex flex-col gap-4 md:col-span-8 xl:col-span-8">
            <LeftChart priceGap={priceGap} />

            <div className="bg-gray-800 p-3 rounded-md">
              <div className="flex flex-wrap items-center justify-between gap-2 text-sm text-gray-400">
                <div className="flex items-center gap-3">
                  <span>6M</span><span>3M</span><span>1M</span><span>5D</span>
                </div>
                <div className="flex items-center gap-2">
                  <FiClock />
                  Auto
                </div>
              </div>
            </div>

            <OrdersTable />
          </div>

          <div className="flex flex-col gap-4 md:col-span-4 xl:col-span-4">
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2">
              <OrderBook priceGap={priceGap} onPriceGapChange={setPriceGap} />
              <TradeHistory />
            </div>

            <BuyPanel balances={balances} />
          </div>
        </div>
      )}
    </div>
  )
}
