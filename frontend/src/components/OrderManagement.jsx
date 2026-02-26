import React from 'react'
import { FiSearch, FiChevronLeft } from 'react-icons/fi'
import OrdersTable from './OrdersTable'
import Profile from './Profile'
import Deposit from './Deposite'
import ManageFunds from './ManageFunds'

export default function OrderManagement({ setView }){
  return (
    <div className="min-h-screen p-4">
      <div className="sticky top-0 z-30 bg-gray-900/60 backdrop-blur-sm px-3 py-2 rounded-b-md mb-4 flex items-center justify-between">
        <button
          type="button"
          onClick={() => setView && setView('home')}
          className="text-sm text-gray-200 hover:text-white flex items-center gap-2"
        >
          <FiChevronLeft className="w-4 h-4" />
          Back
        </button>

        {/* <div className="text-sm text-gray-200">Order management</div> */}

        <div />
      </div>

      <div className="space-y-4">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-lg font-semibold text-gray-100">Order management</h2>
            <div className="mt-2 flex gap-4 text-sm">
              <button className="text-blue-400 border-b-2 border-blue-400 pb-1">Orders</button>
              <button className="text-gray-400">Fills</button>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <Deposit  />
            <ManageFunds />
            <Profile />
          </div>
        </div>

        <div className="bg-gray-800 p-4 rounded-md">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 bg-gray-700 p-2 rounded-md">
                <FiSearch className="w-4 h-4 text-gray-400" />
                <input className="bg-transparent outline-none text-sm text-gray-200" placeholder="Select an asset or market" />
              </div>

              <div className="flex items-center gap-2">
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All types</button>
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All sides</button>
                <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">All statuses</button>
              </div>
            </div>

            <div className="flex items-center gap-3">
              <button className="bg-gray-700 text-gray-200 px-3 py-1 rounded-md text-sm">Visit statements</button>
              <button className="bg-red-600 text-white px-3 py-1 rounded-md text-sm">Cancel all</button>
            </div>
          </div>

          <div className="mt-4">
            <OrdersTable />
          </div>
        </div>
      </div>
    </div>
  )
}
