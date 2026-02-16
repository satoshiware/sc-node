import React from 'react'
import { FiSearch, FiChevronDown } from 'react-icons/fi'
import Profile from './Profile'
import MarketSelect from './MarketSelect'

export default function Header({ setView }){
  return (
    <header className="flex items-center justify-between w-full sticky top-0 z-20 bg-gray-900/50 backdrop-blur-sm px-4 py-3">
      <div className="flex items-center gap-6">
        <MarketSelect />

        <div className="flex items-baseline gap-3">
          <div className="text-xs text-gray-400">Last Price (24H)</div>
          <div className="text-lg font-semibold">$89,406.27 <span className="text-green-400 text-sm">+1.37%</span></div>
        </div>

        <div className="flex items-center gap-4 text-sm text-gray-400">
          <div>
            <div className="text-xs text-gray-400">24H Volume</div>
            <div className="text-sm text-gray-200">$602,737,730.27</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">24H High</div>
            <div className="text-sm text-gray-200">$90,476.81</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">24H Low</div>
            <div className="text-sm text-gray-200">$88,041.30</div>
          </div>
        </div>
      </div>

      <div className="flex items-center gap-4">
        <nav className="flex items-center gap-4">
          {/* <a href="#" className="text-sm text-gray-300 hover:text-white">Exchange</a> */}
          <button type="button" onClick={() => setView && setView('exchange')} className="text-sm text-gray-300 hover:text-white">Exchange</button>
          <button type="button" onClick={() => setView && setView('wallet')} className="text-sm text-gray-300 hover:text-white">Wallet</button>
          <button type="button" onClick={() => setView && setView('orders')} className="text-sm text-gray-300 hover:text-white">Orders</button>
        </nav>

        <Profile />
      </div>
    </header>
  )
}
