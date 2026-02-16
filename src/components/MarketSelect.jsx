import React, { useState, useRef, useEffect } from 'react'
import { FiChevronDown } from 'react-icons/fi'

export default function MarketSelect({ markets = ['BTC-SATS','AZC-SATS','USD-SATS','GLD-SATS','SLV-SATS'], onChange }){
  const [open, setOpen] = useState(false)
  const [selected, setSelected] = useState(markets[0])
  const ref = useRef(null)

  useEffect(() => {
    function handleClick(e){
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [])

  const handleSelect = (m) => {
    setSelected(m)
    setOpen(false)
    if (onChange) onChange(m)
  }

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-3 bg-gray-800 px-3 py-1 rounded-full text-sm"
      >
        <div className="w-7 h-7 rounded-full bg-amber-600 text-white flex items-center justify-center text-xs font-bold">฿</div>
        <div className="font-medium text-sm text-gray-100">{selected}</div>
        <FiChevronDown className="text-gray-400" />
      </button>

      {open && (
        <div className="absolute left-0 mt-2 w-44 bg-gray-800 border border-gray-700 rounded-md shadow-lg z-50 overflow-hidden">
          {markets.map((m) => (
            <button
              key={m}
              type="button"
              onClick={() => handleSelect(m)}
              className={`w-full text-left px-3 py-2 text-sm ${m === selected ? 'bg-gray-700 text-white' : 'text-gray-200 hover:bg-gray-700 hover:text-white'}`}
            >
              {m}
            </button>
          ))}
        </div>
      )}
    </div>
  )
}
