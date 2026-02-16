import React, { useState } from 'react'

export default function BuyPanel(){
  const [tab, setTab] = useState('buy')
  const [orderType, setOrderType] = useState('market')

  const marketDenom = 'AZC' // replace with actual market denom
  const availableBuy = '133.66'
  const availableSell = '1,234,560' // in SATS

  return (
    <div className="bg-gray-800 p-4 rounded-md">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setTab('buy')}
            className={"px-3 py-1 rounded-md text-sm " + (tab === 'buy' ? 'bg-gray-700 text-white' : 'text-gray-400')}
          >
            Buy
          </button>
          <button
            onClick={() => setTab('sell')}
            className={"px-3 py-1 rounded-md text-sm " + (tab === 'sell' ? 'bg-gray-700 text-white' : 'text-gray-400')}
          >
            Sell
          </button>
        </div>

        <div className="text-xs text-gray-400">{orderType === 'market' ? 'Market' : 'Limit'}</div>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <button
          onClick={() => setOrderType('market')}
          className={"px-3 py-1 rounded-md text-sm " + (orderType === 'market' ? 'bg-gray-700 text-white' : 'text-gray-400')}
        >
          Market
        </button>
        <button
          onClick={() => setOrderType('limit')}
          className={"px-3 py-1 rounded-md text-sm " + (orderType === 'limit' ? 'bg-gray-700 text-white' : 'text-gray-400')}
        >
          Limit
        </button>
      </div>

      <div className="space-y-2">
        {/* Available - denomination depends on buy vs sell */}
        <div className="text-xs text-gray-400">Available</div>
        <div className="bg-gray-900 p-2 rounded flex items-center justify-between">
          <div className="text-sm">
            {tab === 'buy' ? marketDenom : 'SATS'}
          </div>
          <div className="text-sm text-gray-400">
            {tab === 'buy' ? `${availableBuy} ${marketDenom}` : `${availableSell} SATS`}
          </div>
        </div>

        <div className="flex gap-2">
          <input className="flex-1 p-2 bg-gray-900 rounded outline-none" placeholder={`Amount (${tab === 'buy' ? marketDenom : 'SATS'})`} />
          <div className="flex items-center space-x-2">
            {orderType === 'market' && (
              <>
                <button className="px-2 py-1 bg-gray-700 rounded text-sm">25%</button>
                <button className="px-2 py-1 bg-gray-700 rounded text-sm">50%</button>
                <button className="px-2 py-1 bg-gray-700 rounded text-sm">Max</button>
              </>
            )}
          </div>
        </div>

        {orderType === 'limit' && (
          <input className="w-full p-2 bg-gray-900 rounded outline-none" placeholder={`Limit price (${tab === 'buy' ? 'SATS' : marketDenom})`} />
        )}

        {orderType === 'market' && (
          <div className="space-y-2">
            <div className="flex items-center justify-between text-sm">
              <div className="text-gray-400">Slippage</div>
              <div className="text-gray-200">0.5%</div>
            </div>
            <div className="flex items-center justify-between text-sm">
              <div className="text-gray-400">Average Price</div>
              <div className="text-gray-200">9,000</div>
            </div>
          </div>
        )}

        <div className="flex items-center justify-between text-sm text-gray-400">
          <div>Subtotal</div>
          <div>$0.00</div>
        </div>
        <div className="flex items-center justify-between text-sm text-gray-400">
          <div>Fee</div>
          <div>$0.00</div>
        </div>
        <div className="flex items-center justify-between text-sm text-gray-200">
          <div>Total</div>
          <div>$0.00</div>
        </div>

        <button
          className={"w-full mt-2 py-2 rounded " + (tab === 'buy' ? 'bg-green-600 text-black' : 'bg-red-600 text-white')}
        >
          {tab === 'buy'
            ? (orderType === 'limit' ? 'Place Limit Buy' : 'Buy SATS')
            : (orderType === 'limit' ? 'Place Limit Sell' : 'Sell SATS')}
        </button>
      </div>
    </div>
  )
}
