import React, { useState, useRef, useEffect } from 'react'
import { FiChevronDown, FiUserPlus, FiSettings, FiMoon, FiLogOut } from 'react-icons/fi'

export default function Profile({ name, email, user, onSignOut }) {
  const displayName = name ?? user?.name ?? 'User'
  const displayEmail = email ?? user?.email ?? ''
  const [open, setOpen] = useState(false)
  const [dark, setDark] = useState(false)
  const wrapperRef = useRef(null)

  useEffect(() => {
    function handleClick(e){
      if (wrapperRef.current && !wrapperRef.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('click', handleClick)
    return () => document.removeEventListener('click', handleClick)
  }, [])

  const handleSignOut = () => {
    onSignOut?.()
    setOpen(false)
  }

  return (
    <div ref={wrapperRef} className="relative">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(v => !v)}
        className="flex items-center gap-2 bg-gray-800 p-1 rounded-md cursor-pointer"
      >
        <div className="w-7 h-7 rounded-full bg-amber-600 text-white flex items-center justify-center text-xs font-bold">{displayName ? displayName[0] : 'U'}</div>
        <div className="text-sm text-gray-200 hidden sm:block">{displayName}</div>
        <FiChevronDown className="text-gray-400" />
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-64 bg-gray-900 border border-gray-800 rounded-lg p-3 shadow-lg">
          <div className="flex items-start gap-3">
            <div className="w-10 h-10 rounded-full bg-sky-500 text-white flex items-center justify-center font-bold">{displayName ? displayName[0] : 'U'}</div>
            <div className="flex-1">
              <div className="text-sm font-semibold text-gray-100">{displayName}</div>
              <div className="text-xs text-gray-400">{displayEmail}</div>
              <a href="#" className="text-sm text-blue-400 mt-1 inline-block">Manage account</a>
            </div>
          </div>

          <div className="mt-3 border-t border-gray-800 pt-2 space-y-2">
            <button
              type="button"
              onClick={() => { /* TODO: wire add account */ alert('Add account') }}
              className="w-full text-left flex items-center gap-3 text-gray-200 hover:text-white px-2 py-1 rounded"
            >
              <FiUserPlus className="w-4 h-4" />
              Add account
            </button>

            <button
              type="button"
              onClick={() => { /* TODO: open settings */ alert('Settings') }}
              className="w-full text-left flex items-center gap-3 text-gray-200 hover:text-white px-2 py-1 rounded"
            >
              <FiSettings className="w-4 h-4" />
              Settings
            </button>

            <div className="flex items-center justify-between px-2 py-1">
              <div className="flex items-center gap-3 text-gray-200"><FiMoon className="w-4 h-4" /> Dark mode</div>
              <label className="relative inline-flex items-center cursor-pointer">
                <input type="checkbox" checked={dark} onChange={() => setDark(d => !d)} className="sr-only" />
                <span className={`${dark ? 'bg-blue-600' : 'bg-gray-600'} w-9 h-5 rounded-full relative inline-block` }>
                  <span className={`${dark ? 'translate-x-4' : 'translate-x-0'} block w-4 h-4 bg-white rounded-full transform transition`} />
                </span>
              </label>
            </div>

            <button
              type="button"
              onClick={handleSignOut}
              className="w-full text-left flex items-center gap-3 text-red-400 hover:text-red-500 px-2 py-1 rounded"
            >
              <FiLogOut className="w-4 h-4" />
              Sign out
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
