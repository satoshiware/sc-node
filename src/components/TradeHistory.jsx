import React from 'react'

export default function TradeHistory(){
  const assetDenom = 'AZC'
  const trades = [
    { amount: '0.005', price: '89,167.97', time: '12:34:30', side: 'buy' },
    { amount: '0.0002', price: '89,167.97', time: '12:34:30', side: 'sell' },
    { amount: '0.00011', price: '89,161.16', time: '12:34:30', side: 'buy' }
,   { amount: '0.0025', price: '89,150.00', time: '12:33:50', side: 'sell' },
    { amount: '0.001', price: '89,145.50', time: '12:33:10', side: 'buy' },
    { amount: '0.003', price: '89,140.75', time: '12:32:45', side: 'sell' },
    { amount: '0.0005', price: '89,135.20', time: '12:32:10', side: 'buy' }
  ]

  return (
    <div className="bg-gray-800 p-3 rounded-md">
      <div className="text-sm font-medium mb-2">Trade history</div>

      <div className="grid grid-cols-3 text-xs text-gray-400 mb-2 px-1">
        <div className="text-left">Amount ({assetDenom})</div>
        <div className="text-center">Price (SATS)</div>
        <div className="text-center">Time</div>
      </div>

      <div className="space-y-1 text-sm text-gray-300 max-h-60 overflow-y-auto pr-2">
        {trades.map((t,i)=> (
          <div key={i} className="grid grid-cols-3 items-center gap-2">
            <div className="text-gray-400">{t.amount}</div>
            <div className={t.side === 'buy' ? 'text-center text-green-400' : 'text-center text-red-400'}>{t.price}</div>
            <div className="text-gray-500 text-right">{t.time}</div>
          </div>
        ))}
      </div>
    </div>
  )
}
