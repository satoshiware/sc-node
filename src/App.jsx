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

export default function App(){
  const [view, setView] = useState('home')

  return (
    <div className="min-h-screen p-4">
      {view === 'home' && <Header setView={setView} />}

      {view === 'orders' ? (
        <OrderManagement setView={setView} />
      ) : view === 'wallet' ? (
        <Wallet setView={setView} />
      ) : view === 'exchange' ? (
        <Exchange setView={setView} />
      ) : (
        <div className="mt-4 grid grid-cols-12 gap-4">
          <div className="col-span-8 space-y-4">
            <LeftChart />

            <div className="bg-gray-800 p-3 rounded-md">
              <div className="flex items-center justify-between text-sm text-gray-400">
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

          <div className="col-span-4 space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <OrderBook />
              <TradeHistory />
            </div>

            <BuyPanel />
          </div>
        </div>
      )}
    </div>
  )
}
