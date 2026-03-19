import React, { useEffect, useRef, useState } from 'react'

const WS_URL = import.meta.env.VITE_WS_URL
const API_URL = import.meta.env.VITE_API_URL

export default function OrdersTable({
  onlyMyOrders = false,
  user = null,
  variant = 'default', // 'default' for home table, 'management' for OrderManagement page
}) {
  const [orders, setOrders] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const isManagementLayout = variant === 'management'

  const wsRef = useRef(null)
  const pollRef = useRef(null)
  const reconnectRef = useRef(null)

  const displayPrice = (p) => {
    if (p == null || p === '0') return '—'
    return typeof p === 'number' ? p.toLocaleString() : p
  }

  const clearPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const clearReconnect = () => {
    if (reconnectRef.current) {
      clearTimeout(reconnectRef.current)
      reconnectRef.current = null
    }
  }

  const closeWs = () => {
    if (wsRef.current) {
      wsRef.current.onclose = null
      wsRef.current.close()
      wsRef.current = null
    }
  }

  const fetchOrders = async () => {
    const endpoint = onlyMyOrders ? '/api/orders/mine' : '/api/orders/poll'
    const headers =
      onlyMyOrders && user?.token
        ? { Authorization: `Bearer ${user.token}` }
        : {}

    const res = await fetch(`${API_URL}${endpoint}`, { headers })
    const data = await res.json()

    if (!res.ok) {
      throw new Error(data?.detail || 'Failed to fetch orders')
    }

    setOrders(data.orders || [])
    setError(null)
    setLoading(false)
  }

  const startPolling = () => {
    clearPolling()
    fetchOrders().catch((err) => {
      console.error('Polling error:', err)
      setError(err.message || 'Failed to fetch orders')
      setLoading(false)
    })

    pollRef.current = setInterval(() => {
      fetchOrders().catch((err) => {
        console.error('Polling error:', err)
        setError(err.message || 'Failed to fetch orders')
      })
    }, 2000)
  }

  const connectWebSocket = () => {
    try {
      const websocket = new WebSocket(`${WS_URL}/ws/orders`)
      wsRef.current = websocket

      websocket.onopen = () => {
        setLoading(false)
        setError(null)
      }

      websocket.onmessage = (event) => {
        const data = JSON.parse(event.data)
        if (data.type === 'initial' || data.type === 'update') {
          setOrders(data.orders || [])
          setError(null)
        }
      }

      websocket.onerror = (event) => {
        console.error('WebSocket error:', event)
        setError('Failed to connect to order updates')
        setLoading(false)
        closeWs()
        startPolling()
      }

      websocket.onclose = () => {
        if (onlyMyOrders) return
        clearReconnect()
        reconnectRef.current = setTimeout(() => {
          connectWebSocket()
        }, 3000)
      }
    } catch (err) {
      console.error('WebSocket connection error:', err)
      setError('Failed to establish WebSocket connection')
      setLoading(false)
      startPolling()
    }
  }

  useEffect(() => {
    setLoading(true)
    setError(null)

    clearPolling()
    clearReconnect()
    closeWs()

    if (onlyMyOrders) {
      startPolling()
    } else {
      connectWebSocket()
    }

    return () => {
      clearPolling()
      clearReconnect()
      closeWs()
    }
  }, [onlyMyOrders, user?.token])

  const handleCancel = (order) => {
    alert(`Cancel requested for order placed ${order.time}`)
    // TODO: wire to real cancel API
  }

  if (loading) return <div className="text-gray-400">Connecting to orders...</div>
  if (error) return <div className="text-red-400">Error: {error}</div>
  if (orders.length === 0) return <div className="text-gray-400">No open orders</div>

  return (
    <div className="bg-gray-800 p-3 rounded-md mt-2 min-w-0 overflow-x-auto">
      <div className="text-sm font-medium mb-2">Order</div>
      <div
        className={
          isManagementLayout
            ? 'grid gap-1 sm:gap-2 text-xs text-gray-400 mb-2 px-1 border-b border-gray-700 pb-2 min-w-[980px] grid-cols-[150px_80px_80px_110px_120px_120px_120px_90px_110px]'
            : 'grid grid-cols-9 gap-1 sm:gap-2 text-xs text-gray-400 mb-2 px-1 border-b border-gray-700 pb-2 min-w-[600px]'
        }
      >
        <div>Time Placed</div>
        <div>Type</div>
        <div>Side</div>
        <div>Price (SATS)</div>
        <div>Amount</div>
        <div>Remaining</div>
        <div>Total</div>
        <div>Status</div>
        <div className="text-right">Actions</div>
      </div>

      <div className="mt-2 space-y-2 text-xs sm:text-sm max-h-48 sm:max-h-56 md:max-h-64 overflow-y-auto pr-2 scrollbar-dark">
        {orders.map((o, i) => (
          <div
            key={o.id || i}
            className={
              isManagementLayout
                ? 'grid gap-1 sm:gap-2 text-gray-200 items-center min-w-[980px] grid-cols-[150px_80px_80px_110px_120px_120px_120px_90px_110px]'
                : 'grid grid-cols-9 gap-1 sm:gap-2 text-gray-200 items-center min-w-[600px]'
            }
          >
            <div className={isManagementLayout ? 'text-xs text-gray-200 whitespace-nowrap' : 'text-xs text-gray-200 truncate'}>{o.time}</div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>{o.type}</div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>{o.side}</div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>{displayPrice(o.priceSats)}</div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>
              {o.quantity != null ? `${parseFloat(o.quantity).toFixed(8)} AZC` : '—'}
            </div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>{o.amount}</div>
            <div className={isManagementLayout ? 'whitespace-nowrap' : 'truncate'}>{o.total}</div>
            <div className={o.status === 'Open' ? 'text-green-300' : o.status === 'Filled' ? 'text-gray-400' : 'text-yellow-300'}>
              {o.status}
            </div>
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