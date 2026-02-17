import React, { useState } from 'react'

function Row({price,amount,side}){
  return (
    <div className="flex justify-between text-sm text-gray-300">
      <div className="text-gray-300">{amount}</div>
      <div className={side === 'ask' ? 'text-red-400 text-right' : 'text-green-400 text-right'}>{price}</div>
    </div>
  )
}

export default function OrderBook(){
  const [depth, setDepth] = useState(10)
  const asks = [['89,460', '0.14'], ['89,450','2.45'], ['89,440','2.27']]
  const bids = [['89,058','0.51'], ['89,050','11.32'], ['89,040','0.14']]

  return (
    <div className="bg-gray-800 p-3 rounded-md">
      <div className="flex items-center justify-between mb-2">
        <div className="text-sm font-medium">Order book</div>
        <div className="text-xs text-gray-400">
          <div className="flex items-center space-x-2">
            <button
              onClick={() => setDepth(d => Math.max(1, d - 1))}
              className="px-2 py-1 bg-gray-900 rounded text-sm"
            >-</button>
            <div className="px-2 py-1 bg-gray-900 rounded text-sm">{depth}</div>
            <button
              onClick={() => setDepth(d => Math.min(100, d + 1))}
              className="px-2 py-1 bg-gray-900 rounded text-sm"
            >+</button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 text-xs text-gray-400 mb-2 px-1">
        <div>Amount (AZC)</div>
        <div className="text-right">Price (SATS)</div>
      </div>

      <div className="space-y-1">
        {asks.map((a,i)=>(<Row key={i} price={a[0]} amount={a[1]} side="ask"/>))}
        <div className="h-px bg-gray-700 my-1" />
        {bids.map((b,i)=>(<Row key={i} price={b[0]} amount={b[1]} side="bid"/>))}
      </div>
    </div>
  )
}
