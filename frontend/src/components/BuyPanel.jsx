import React, { useState } from 'react'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function BuyPanel({ balances, user, onWalletRefresh }) {
  const [tab, setTab]             = useState('buy')
  const [orderType, setOrderType] = useState('market')
  const [amount, setAmount]       = useState('')
  const [limitPrice, setLimitPrice] = useState('')
  const [status, setStatus]       = useState(null) // null | 'loading' | 'success' | 'error'
  const [errorMsg, setErrorMsg]   = useState('')

  const availAzc  = balances?.azc  ?? 0
  const availSats = balances?.sats ?? 0

  function switchTab(t) {
    setTab(t)
    setAmount('')
    setLimitPrice('')
    setStatus(null)
  }

  function switchOrderType(t) {
    setOrderType(t)
    setLimitPrice('')
    setStatus(null)
  }

  // % buttons fill AZC amount:
  //   sell → fraction of AZC balance (you're selling AZC)
  //   buy  → fraction of AZC balance as a rough target quantity
  function fillPct(pct) {
    setAmount((availAzc * pct).toFixed(8))
  }

  const amtNum   = parseFloat(amount)   || 0
  const priceNum = parseFloat(limitPrice) || 0

  const subtotalSats = (orderType === 'limit' && amtNum > 0 && priceNum > 0)
    ? (amtNum * priceNum).toLocaleString('en-US', { maximumFractionDigits: 0 }) + ' SATS'
    : '—'

  const isValid = amtNum > 0 && (orderType === 'market' || priceNum > 0)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!isValid) return

    setStatus('loading')
    setErrorMsg('')

    const body = {
      side:     tab,
      type:     orderType,
      price:    orderType === 'limit' ? priceNum : null,
      quantity: amtNum,
    }

        try {
      const res = await fetch(`${API_URL}/api/orders`, {
        method:  'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(user?.token ? { 'Authorization': `Bearer ${user.token}` } : {}),
        },
        body: JSON.stringify(body),
      })
      const data = await res.json()

      if (!res.ok) {
        setStatus('error')
        setErrorMsg(data.detail || 'Failed to place order')
      } else {
        setStatus('success')
        setAmount('')
        setLimitPrice('')
        onWalletRefresh?.()                    // ← trigger wallet re-fetch in App.jsx
        setTimeout(() => setStatus(null), 3000)
      }
    } catch {
      setStatus('error')
      setErrorMsg('Network error — is the backend running?')
    }
  }

  return (
    <div className="bg-gray-800 p-3 sm:p-4 rounded-md min-w-0">

      {/* ── Buy / Sell tabs ── */}
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-3">
        <div className="flex items-center gap-2">
          <button
            onClick={() => switchTab('buy')}
            className={"px-3 py-1 rounded-md text-sm " + (tab === 'buy' ? 'bg-gray-700 text-white' : 'text-gray-400')}
          >Buy</button>
          <button
            onClick={() => switchTab('sell')}
            className={"px-3 py-1 rounded-md text-sm " + (tab === 'sell' ? 'bg-gray-700 text-white' : 'text-gray-400')}
          >Sell</button>
        </div>
        <div className="text-xs text-gray-400">{orderType === 'market' ? 'Market' : 'Limit'}</div>
      </div>

      {/* ── Market / Limit tabs ── */}
      <div className="mb-3 flex items-center gap-2">
        <button
          onClick={() => switchOrderType('market')}
          className={"px-3 py-1 rounded-md text-sm " + (orderType === 'market' ? 'bg-gray-700 text-white' : 'text-gray-400')}
        >Market</button>
        <button
          onClick={() => switchOrderType('limit')}
          className={"px-3 py-1 rounded-md text-sm " + (orderType === 'limit' ? 'bg-gray-700 text-white' : 'text-gray-400')}
        >Limit</button>
      </div>

      <form onSubmit={handleSubmit} className="space-y-2">

        {/* ── Available balance ── */}
        <div className="text-xs text-gray-400">Available</div>
        <div className="bg-gray-900 p-2 rounded flex items-center justify-between gap-2">
          <span className="text-sm">{tab === 'buy' ? 'SATS' : 'AZC'}</span>
          <span className="text-sm text-gray-300 font-mono">
            {tab === 'buy'
              ? availSats.toLocaleString() + ' SATS'
              : availAzc.toFixed(8) + ' AZC'}
          </span>
        </div>

        {/* ── Amount + % buttons ── */}
        <div className="flex flex-col gap-2 sm:flex-row sm:gap-2">
          <input
            type="number"
            min="0"
            step="any"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            className="flex-1 min-w-0 p-2 bg-gray-900 rounded outline-none w-full text-gray-100 placeholder-gray-500 [appearance:textfield]"
            placeholder="Amount (AZC)"
          />
          <div className="flex items-center gap-1">
            <button type="button" onClick={() => fillPct(0.25)} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">25%</button>
            <button type="button" onClick={() => fillPct(0.50)} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">50%</button>
            <button type="button" onClick={() => fillPct(1.00)} className="px-2 py-1 bg-gray-700 hover:bg-gray-600 rounded text-xs">Max</button>
          </div>
        </div>

        {/* ── Limit price ── */}
        {orderType === 'limit' && (
          <input
            type="number"
            min="0"
            step="any"
            value={limitPrice}
            onChange={(e) => setLimitPrice(e.target.value)}
            className="w-full min-w-0 p-2 bg-gray-900 rounded outline-none text-gray-100 placeholder-gray-500 [appearance:textfield]"
            placeholder="Limit price (SATS per AZC)"
          />
        )}

        {/* ── Market info ── */}
        {orderType === 'market' && (
          <div className="space-y-1 pt-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Slippage</span>
              <span className="text-gray-200">0.5%</span>
            </div>
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-400">Avg Price</span>
              <span className="text-gray-400">— (filled by matcher)</span>
            </div>
          </div>
        )}

        {/* ── Subtotal / Fee / Total ── */}
        <div className="pt-1 space-y-1 border-t border-gray-700">
          <div className="flex items-center justify-between text-sm text-gray-400">
            <span>Subtotal</span>
            <span className="font-mono">{subtotalSats}</span>
          </div>
          <div className="flex items-center justify-between text-sm text-gray-400">
            <span>Fee</span>
            <span>—</span>
          </div>
          <div className="flex items-center justify-between text-sm text-gray-200 font-medium">
            <span>Total</span>
            <span className="font-mono">{subtotalSats}</span>
          </div>
        </div>

        {/* ── Feedback banner ── */}
        {status === 'success' && (
          <div className="text-sm text-green-400 bg-green-900/30 border border-green-800 rounded px-3 py-2">
            ✓ Order placed successfully!
          </div>
        )}
        {status === 'error' && (
          <div className="text-sm text-red-400 bg-red-900/30 border border-red-800 rounded px-3 py-2">
            {errorMsg}
          </div>
        )}

        {/* ── Submit ── */}
        <button
          type="submit"
          disabled={!isValid || status === 'loading'}
          className={
            "w-full mt-1 py-2 rounded text-sm sm:text-base font-medium transition-opacity " +
            "disabled:opacity-50 disabled:cursor-not-allowed " +
            (tab === 'buy' ? 'bg-green-600 hover:bg-green-500 text-black' : 'bg-red-600 hover:bg-red-500 text-white')
          }
        >
          {status === 'loading'
            ? 'Placing…'
            : tab === 'buy'
              ? (orderType === 'limit' ? 'Place Limit Buy' : 'Buy AZC')
              : (orderType === 'limit' ? 'Place Limit Sell' : 'Sell AZC')}
        </button>

      </form>
    </div>
  )
}
