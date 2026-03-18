import React from 'react'
import { FiSearch, FiChevronLeft } from 'react-icons/fi'
import OrdersTable from './OrdersTable'
import Profile from './Profile'
import Deposit from './Deposite'
import ManageFunds from './ManageFunds'

export default function OrderManagement({ setView, user, onSignOut }){
  return (
    <div className="min-h-screen p-2 sm:p-4">
      <div className="max-w-6xl mx-auto">
        <div className="sticky top-0 z-30 bg-gray-900/60 backdrop-blur-sm px-3 py-2 rounded-b-md mb-4 flex items-center justify-between">
          <button
            type="button"
            onClick={() => setView && setView('home')}
            className="text-sm text-gray-200 hover:text-white flex items-center gap-2"
          >
            <FiChevronLeft className="w-4 h-4" />
            Back
          </button>

          <div />
        </div>

        <div className="space-y-4">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Order management</h2>
            <div className="mt-2 flex flex-wrap gap-4 text-sm">
              <button className="text-blue-400 border-b-2 border-blue-400 pb-1">Orders</button>
              <button className="text-gray-400">Fills</button>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2 md:gap-3">
            <Deposit />
            <ManageFunds />
            <Profile user={user} onSignOut={onSignOut} />
          </div>
        </div>

        <div className="bg-gray-800 p-3 sm:p-4 rounded-md min-w-0">
          <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
            <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center sm:gap-3">
              <div className="flex items-center gap-2 bg-gray-700 p-2 rounded-md min-w-0">
                <FiSearch className="w-4 h-4 text-gray-400 flex-shrink-0" />
                <input className="bg-transparent outline-none text-sm text-gray-200 w-full min-w-0" placeholder="Select an asset or market" />
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All types</button>
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All sides</button>
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All statuses</button>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-2 md:gap-3">
              <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">Visit statements</button>
              <button className="bg-red-600 text-white px-3 py-1 rounded-md text-sm">Cancel all</button>
            </div>
          </div>

          <div className="mt-4 min-w-0">
            <OrdersTable onlyMyOrders={true} user={user} />
          </div>
        </div>
        </div>
      </div>
    </div>
  )
}
