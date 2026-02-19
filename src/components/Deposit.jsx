import React, { useState, useRef, useEffect } from 'react'
import { FiDownload, FiDollarSign } from 'react-icons/fi'

export default function Deposit() {
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

  const handleDepositCash = () => {
    // TODO: Wire to deposit cash modal/page
    console.log('Deposit cash clicked')
    setIsOpen(false)
  }

  const handleDepositCrypto = () => {
    // TODO: Wire to deposit crypto modal/page
    console.log('Deposit crypto clicked')
    setIsOpen(false)
  }

  return (
    <div className="relative" ref={menuRef}>
      {/* Deposit Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-full text-sm font-medium transition-colors flex items-center gap-2"
      >
        <FiDownload size={16} />
        Deposit
      </button>

      {/* Dropdown Menu */}
      {isOpen && (
        <div className="absolute top-full mt-2 left-0 bg-gray-800 border border-gray-700 rounded-lg shadow-lg w-56 z-50">
          {/* Deposit Cash Option */}
          <button
            onClick={handleDepositCash}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-700 transition-colors border-b border-gray-700 first:rounded-t-lg"
          >
            <FiDollarSign size={20} className="text-gray-300 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <div className="text-sm font-medium text-white">Deposit cash</div>
              <div className="text-xs text-gray-400">Add funds from your bank account</div>
            </div>
          </button>

          {/* Deposit Crypto Option */}
          <button
            onClick={handleDepositCrypto}
            className="w-full px-4 py-3 flex items-start gap-3 hover:bg-gray-700 transition-colors last:rounded-b-lg"
          >
            <FiDownload size={20} className="text-gray-300 mt-0.5 flex-shrink-0" />
            <div className="text-left">
              <div className="text-sm font-medium text-white">Deposit crypto</div>
              <div className="text-xs text-gray-400">From another account or crypto wallet</div>
            </div>
          </button>
        </div>
      )}
    </div>
  )
}
