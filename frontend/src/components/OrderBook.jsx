// frontend/src/components/OrderBook.jsx
import React, { useState, useEffect, useRef } from 'react'

function Row({price, amount, side}){
  return (
    <div className="flex justify-between text-sm text-gray-300">
      <div className="text-gray-300">{amount}</div>
      <div className={side === 'ask' ? 'text-red-400 text-right' : 'text-green-400 text-right'}>{price}</div>
    </div>
  )
}

export default function OrderBook(){
  const [depth, setDepth] = useState(10)
  const [asks, setAsks] = useState([])
  const [bids, setBids] = useState([])
  const wsRef = useRef(null)

  useEffect(() => {
    connectWebSocket()
    return () => {
      if (wsRef.current) wsRef.current.close()
    }
  }, [])

  const connectWebSocket = () => {
    try {
      const websocket = new WebSocket('ws://localhost:8000/ws/orders')
      wsRef.current = websocket

      websocket.onopen = () => {
        console.log('[OrderBook] Connected')
      }

      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'initial' || data.type === 'update') {
            updateOrderBook(data.orders || [])
          }
        } catch (err) {
          console.error('[OrderBook] Parse error:', err)
        }
      }

      websocket.onclose = () => {
        console.log('[OrderBook] Disconnected, reconnecting...')
        setTimeout(connectWebSocket, 2000)
      }

      websocket.onerror = (err) => {
        console.error('[OrderBook] Error:', err)
      }
    } catch (err) {
      console.error('[OrderBook] Connection failed:', err)
    }
  }

  const updateOrderBook = (orders) => {
    // Filter: Limit orders with remaining_quantity > 0 and status Open or Partial
    const limitOrders = orders.filter(
      o => o.type === 'Limit' && o.remaining_quantity > 0 && (o.status === 'Open' || o.status === 'Partial')
    )

    // Parse prices and amounts
    const parsed = limitOrders.map(o => {
      const price = parseInt(String(o.priceSats).replace(/,/g, ''), 10) || 0
      const amount = parseFloat(String(o.amount).replace(/ AZC/i, '')) || 0
      return {
        id: o.id,
        price,
        amount: amount.toFixed(8),
        side: o.side
      }
    })

    // Separate and sort asks (Sell orders, descending price)
    const asksList = parsed
      .filter(o => o.side === 'Sell' && o.price > 0)
      .sort((a, b) => b.price - a.price)
      .slice(0, depth)

    // Separate and sort bids (Buy orders, descending price)
    const bidsList = parsed
      .filter(o => o.side === 'Buy' && o.price > 0)
      .sort((a, b) => b.price - a.price)
      .slice(0, depth)

    setAsks(asksList)
    setBids(bidsList)
  }

  return (
    <div className="bg-gray-800 p-3 rounded-md min-w-0">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between mb-2">
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

      <div className="grid grid-cols-2 text-xs text-gray-400 mb-2 px-1 border-b border-gray-700 pb-2">
        <div>Amount (AZC)</div>
        <div className="text-right">Price (SATS)</div>
      </div>

      <div className="space-y-1 overflow-y-auto h-48 sm:h-64 md:h-80 lg:h-96 pr-2">
        {asks.map((a, i) => (
          <Row key={`ask-${a.id || i}`} price={a.price.toLocaleString()} amount={a.amount} side="ask" />
        ))}
        {(asks.length > 0 || bids.length > 0) && <div className="h-px bg-gray-700 my-1" />}
        {bids.map((b, i) => (
          <Row key={`bid-${b.id || i}`} price={b.price.toLocaleString()} amount={b.amount} side="bid" />
        ))}
      </div>
    </div>
  )
}