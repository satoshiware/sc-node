import React, { useState, useRef, useEffect } from 'react'
import { FiArrowUp, FiEdit3, FiRefreshCw } from 'react-icons/fi'

export default function ManageFunds() {
  const [isOpen, setIsOpen] = useState(false)
  const menuRef = useRef(null)

  // Close menu when clicking outside
  useEffect(() => {
    function handleClickOutside(event) {
      if (menuRef.current && !menuRef.current.contains(event.target)) {
        setIsOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const handleWithdrawCrypto = () => {
    // TODO: Wire to withdraw crypto modal/page
    console.log('Withdraw crypto clicked')
    setIsOpen(false)
  }

  const handleConvertCash = () => {
    // TODO: Wire to convert cash modal/page
    console.log('Convert cash clicked')
    setIsOpen(false)
  }

  const handleConvertCrypto = () => {
    // TODO: Wire to convert crypto modal/page
    console.log('Convert crypto clicked')
    setIsOpen(false)
  }

  return (
    <div className="relative" ref={menuRef}>
      {/* Manage funds Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-full text-sm font-medium transition-colors"
      >
        Manage funds
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full mt-2 left-0 bg-gray-800 border border-gray-700 rounded-lg shadow-lg w-56 z-50">
          {/* Total Balance Section */}
          <div className="px-4 py-4 border-b border-gray-700">
            <div className="text-xs text-gray-400 mb-2">Total balance</div>
            <div className="flex items-baseline gap-2">
              <div className="text-2xl font-semibold text-white">$21.54</div>
              <div className="text-sm text-red-400">↘ $0.14 (0.68%) 1D</div>
            </div>
          </div>

          {/* Withdraw Crypto Option */}
          <button
            onClick={handleWithdrawCrypto}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-700 transition-colors border-b border-gray-700 first:rounded-t-lg"
          >
            <FiArrowUp size={20} className="text-gray-300 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <div className="text-sm font-medium text-white">Withdraw crypto</div>
              <div className="text-xs text-gray-400">To a crypto address, email or phone number</div>
            </div>
          </button>

          {/* Convert Cash Option */}
          <button
            onClick={handleConvertCash}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-700 transition-colors border-b border-gray-700"
          >
            <FiEdit3 size={20} className="text-gray-300 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <div className="text-sm font-medium text-white">Convert cash</div>
              <div className="text-xs text-gray-400">Convert between cash and crypto</div>
            </div>
          </button>

          {/* Convert Crypto Option */}
          <button
            onClick={handleConvertCrypto}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-700 transition-colors last:rounded-b-lg"
          >
            <FiRefreshCw size={20} className="text-gray-300 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <div className="text-sm font-medium text-white">Convert crypto</div>
              <div className="text-xs text-gray-400">Convert crypto to crypto</div>
            </div>
          </button>
        </div>
      )}
    </div>
  )
}
