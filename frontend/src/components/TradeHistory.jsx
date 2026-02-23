import React, { useState, useEffect, useRef } from 'react'

export default function TradeHistory(){
  const [trades, setTrades] = useState([])
  const wsRef = useRef(null)
  const reconnectRef = useRef(null)

  useEffect(() => {
    connectWebSocket()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
    }
  }, [])

  const connectWebSocket = () => {
    try {
      const websocket = new WebSocket('ws://localhost:8000/ws/trades')
      wsRef.current = websocket

      websocket.onopen = () => {
        console.log('[TradeHistory] WS connected')
      }

      websocket.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === 'initial' || data.type === 'update') {
            // Sort trades: newest first
            const sortedTrades = (data.trades || []).sort((a, b) => {
              return new Date(b.time) - new Date(a.time)
            })
            setTrades(sortedTrades)
          }
        } catch (err) {
          console.error('[TradeHistory] Parse error:', err)
        }
      }

      websocket.onerror = (err) => {
        console.error('[TradeHistory] WS error:', err)
      }

      websocket.onclose = () => {
        console.log('[TradeHistory] WS closed, reconnecting...')
        reconnectRef.current = setTimeout(connectWebSocket, 2000)
      }
    } catch (err) {
      console.error('[TradeHistory] Connection failed:', err)
      reconnectRef.current = setTimeout(connectWebSocket, 2000)
    }
  }

  return (
    <div className="bg-gray-800 p-3 rounded-md mt-2">
      <div className="text-xs text-gray-400 mb-2">Trade History</div>
      
      <div className="text-xs text-gray-400 grid grid-cols-4 gap-2 border-b border-gray-700 pb-2">
        <div>Time</div>
        <div>Price (SATS)</div>
        <div>Amount (AZC)</div>
      </div>

      <div className="mt-2 space-y-1 text-sm max-h-80 overflow-y-auto pr-2">
        {trades.length === 0 ? (
          <div className="text-xs text-gray-500 py-4">No trades yet</div>
        ) : (
          trades.map((t, i) => {
            // Extract time HH:MM:SS from full timestamp
            const timeStr = t.time.split(' ')[1] || t.time
            
            // Parse amount from "0.005 AZC" format
            const amount = t.quantity.replace(' AZC', '')
            
            // Determine side color (buy = green, sell = red)
            const sideColor = t.side === 'buy' 
              ? 'text-green-400' 
              : 'text-red-400'
            
            return (
              <div key={t.id || i} className="grid grid-cols-4 gap-2 text-gray-200 items-center py-1 hover:bg-gray-700 px-1 rounded">
                <div className="text-xs text-gray-300">{timeStr}</div>
                <div className={`font-mono ${sideColor}`}>{t.price}</div>
                <div className="font-mono">{amount}</div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}