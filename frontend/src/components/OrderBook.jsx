import React, { useState, useEffect, useRef } from 'react'

const PRICE_GAP_OPTIONS = [1, 5, 10, 25, 50, 100, 250, 500]

function Row({ price, amount, side }) {
  return (
    <div className="flex justify-between text-sm text-gray-300">
      <div>{amount}</div>
      <div className={side === 'ask'
        ? 'text-red-400 text-right'
        : 'text-green-400 text-right'}
      >
        {price}
      </div>
    </div>
  )
}

function bucketOrders(parsed, priceGap, side) {
  const map = new Map()
  for (const o of parsed) {
    if (o.side !== side || o.price <= 0) continue
    const bucket = Math.floor(o.price / priceGap) * priceGap
    const existing = map.get(bucket) || { price: bucket, amount: 0 }
    existing.amount += parseFloat(o.amount) || 0
    map.set(bucket, existing)
  }
  const list = Array.from(map.values()).filter(o => o.amount > 0)
  return side === 'Sell'
    ? list.sort((a, b) => a.price - b.price)
    : list.sort((a, b) => b.price - a.price)
}

export default function OrderBook({ priceGap, onPriceGapChange }) {
  const [rowDepth, setRowDepth] = useState(10)
  const currentIndex = PRICE_GAP_OPTIONS.indexOf(priceGap)
  const [asks, setAsks]         = useState([])
  const [bids, setBids]         = useState([])

  const wsRef       = useRef(null)
  const ordersRef   = useRef([])
  const priceGapRef = useRef(priceGap)   // ← always holds latest priceGap
  const rowDepthRef = useRef(rowDepth)   // ← always holds latest rowDepth

  // keep refs in sync with props/state
  useEffect(() => { priceGapRef.current = priceGap  }, [priceGap])
  useEffect(() => { rowDepthRef.current = rowDepth  }, [rowDepth])

  useEffect(() => {
    connectWebSocket()
    return () => wsRef.current?.close()
  }, [])

  // re-bucket on priceGap or rowDepth change
  useEffect(() => {
    updateOrderBook(ordersRef.current)
  }, [priceGap, rowDepth])

  const connectWebSocket = () => {
    const websocket = new WebSocket('ws://localhost:8000/ws/orders')
    wsRef.current = websocket

    websocket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'initial' || data.type === 'update') {
          ordersRef.current = data.orders || []
          updateOrderBook(ordersRef.current)  // reads from refs — always fresh
        }
      } catch (err) {
        console.error('[OrderBook] Parse error:', err)
      }
    }

    websocket.onclose = () => {
      setTimeout(connectWebSocket, 2000)
    }
  }

  const updateOrderBook = (orders) => {
    // ← read from refs, not closure values
    const gap   = priceGapRef.current
    const depth = rowDepthRef.current

    const limitOrders = orders.filter(
      o => o.type === 'Limit' &&
           o.remaining_quantity > 0 &&
           (o.status === 'Open' || o.status === 'Partial')
    )

    const parsed = limitOrders.map(o => ({
      price:  parseInt(String(o.priceSats).replace(/,/g, ''), 10) || 0,
      amount: parseFloat(String(o.amount).replace(/ AZC/i, '')) || 0,
      side:   o.side,
    }))

    const asksList = bucketOrders(parsed, gap, 'Sell').slice(0, depth)
    const bidsList = bucketOrders(parsed, gap, 'Buy').slice(0, depth)

    setAsks(asksList)
    setBids(bidsList)
  }

  return (
    <div className="bg-gray-800 p-3 rounded-md min-w-0 ">

      <div className="flex items-center justify-between mb-3">

        <div className="text-sm font-medium">
          Order Book
        </div>

        {/* GAP CONTROL */}
        <div className="flex items-center space-x-1">
          <span className="text-xs text-gray-400">
          Gap :
        </span>
        
          <button
            onClick={() =>
            {
              const newIndex = Math.max(0, currentIndex - 1)
              onPriceGapChange(PRICE_GAP_OPTIONS[newIndex])
            }}
            className="px-2 py-1 bg-gray-900 rounded text-sm"
          >
            -
          </button>

          <div className="px-3 py-1 bg-gray-900 rounded text-sm">
            {priceGap}
          </div>

          <button
            onClick={() =>
            {
              const newIndex = Math.min(PRICE_GAP_OPTIONS.length - 1, currentIndex + 1)
              onPriceGapChange(PRICE_GAP_OPTIONS[newIndex])
            }
            }
            className="px-2 py-1 bg-gray-900 rounded text-sm"
          >
            +
          </button>
        </div>
      </div>

      {/* ROW DEPTH CONTROL */}
      <div className="flex items-center space-x-1 mb-3">
        <span className="text-xs text-gray-400">Rows :</span>

        <button
          onClick={() => setRowDepth(d => Math.max(1, d - 1))}
          className="px-2 py-1 bg-gray-900 rounded text-xs"
        >
          -
        </button>

        <div className="px-2 py-1 bg-gray-900 rounded text-xs">
          {rowDepth}
        </div>

        <button
          onClick={() => setRowDepth(d => Math.min(100, d + 1))}
          className="px-2 py-1 bg-gray-900 rounded text-xs"
        >
          +
        </button>
      </div>

      <div className="grid grid-cols-2 text-xs text-gray-400 mb-2 px-1 border-b border-gray-700 pb-2">
        <div>Amount (AZC)</div>
        <div className="text-right">Price (SATS)</div>
      </div>

      <div className="space-y-1 overflow-y-auto h-80 pr-2 scrollbar-dark">
        {[...asks].reverse().map((a, i) => (
          <Row
            key={`ask-${a.price}-${i}`}
            price={a.price.toLocaleString()}
            amount={a.amount.toFixed(8)}
            side="ask"
          />
        ))}

        {(asks.length > 0 || bids.length > 0) &&
          <div className="h-px bg-gray-700 my-1" />}

        {bids.map((b, i) => (
          <Row
            key={`bid-${b.price}-${i}`}
            price={b.price.toLocaleString()}
            amount={b.amount.toFixed(8)}
            side="bid"
          />
        ))}
      </div>

    </div>
  )
}