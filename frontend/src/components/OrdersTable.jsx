import React, { useState, useEffect } from 'react'

export default function OrdersTable(){
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [ws, setWs] = useState(null)

  useEffect(() => {
    connectWebSocket()
    return () => {
      if (ws) {
        ws.close()
      }
    }
  }, [])

  const connectWebSocket = () => {
    try {
      const websocket = new WebSocket('ws://localhost:8000/ws/orders')
      
      websocket.onopen = () => {
        console.log('WebSocket connected')
        setLoading(false)
      }

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'initial' || data.type === 'update') {
          setOrders(data.orders || [])
          setError(null)
        }
      }

      websocket.onerror = (error) => {
        console.error('WebSocket error:', error)
        setError('Failed to connect to order updates')
        setLoading(false)
        // Fallback to polling
        startPolling()
      }

      websocket.onclose = () => {
        console.log('WebSocket disconnected, attempting to reconnect...')
        // Attempt to reconnect after 3 seconds
        setTimeout(connectWebSocket, 3000)
      }

      setWs(websocket)
    } catch (err) {
      console.error('WebSocket connection error:', err)
      setError('Failed to establish WebSocket connection')
      setLoading(false)
      // Fallback to polling
      startPolling()
    }
  }

  const startPolling = () => {
    // Fallback: poll every 2 seconds
    const interval = setInterval(() => {
      fetch('http://localhost:8000/api/orders/poll')
        .then(res => res.json())
        .then(data => {
          setOrders(data.orders || [])
          setError(null)
          setLoading(false)
        })
        .catch(err => {
          console.error('Polling error:', err)
          setError('Failed to fetch orders')
        })
    }, 2000)

    return () => clearInterval(interval)
  }

  const handleCancel = (order) => {
    alert(`Cancel requested for order placed ${order.time}`)
    // TODO: wire to real cancel API
  }

  if (loading) return <div className="text-gray-400">Connecting to orders...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (orders.length === 0) return <div className="text-gray-400">No open orders</div>

  return (
    <div className="bg-gray-800 p-3 rounded-md mt-2">
      <div className="text-xs text-gray-400 mb-1">Order</div>
      <div className="text-xs text-gray-400 grid grid-cols-8 gap-2 border-b border-gray-700 pb-2">
        <div>Time Placed</div>
        <div>Type</div>
        <div>Side</div>
        <div>Price (SATS)</div>
        <div>Amount</div>
        <div>Total</div>
        <div>Status</div>
        <div className="text-right">Actions</div>
      </div>

      <div className="mt-2 space-y-2 text-sm">
        {orders.map((o,i)=> (
          <div key={o.id || i} className="grid grid-cols-8 gap-2 text-gray-200 items-center">
            <div className="text-xs text-gray-200">{o.time}</div>
            <div>{o.type}</div>
            <div>{o.side}</div>
            <div>{o.priceSats}</div>
            <div>{o.amount}</div>
            <div>{o.total}</div>
            <div className={o.status === 'Open' ? 'text-green-300' : o.status === 'Filled' ? 'text-gray-400' : 'text-yellow-300'}>{o.status}</div>
            <div className="text-right">
              {o.status === 'Open' && o.type === 'Limit' ? (
                <button onClick={() => handleCancel(o)} className="text-sm text-red-400 hover:underline">Cancel</button>
              ) : (
                <span className="text-gray-500 text-xs">—</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}