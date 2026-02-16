import React from 'react'

export default function OrdersTable(){
  const orders = [
    { time: '1/20/26 21:20:54', type: 'Limit', side: 'Buy', priceSats: '8,485,976', amount: '1.18182293 AZC', total: '10,028,000', status: 'Open' },
    { time: '1/25/26 16:29:24', type: 'Limit', side: 'Buy', priceSats: '8,639,295', amount: '1.16534551 AZC', total: '10,065,000', status: 'Filled' },
    { time: '1/18/26 18:12:28', type: 'Market', side: 'Buy', priceSats: '9,277,301', amount: '1.07725502 AZC', total: '10,000,000', status: 'Partial' },
    { time: '1/20/26 21:20:54', type: 'Limit', side: 'Buy', priceSats: '8,485,976', amount: '1.18182293 AZC', total: '10,028,000', status: 'Open' },
    { time: '1/25/26 16:29:24', type: 'Limit', side: 'Buy', priceSats: '8,639,295', amount: '1.16534551 AZC', total: '10,065,000', status: 'Filled' },
    { time: '1/18/26 18:12:28', type: 'Market', side: 'Buy', priceSats: '9,277,301', amount: '1.07725502 AZC', total: '10,000,000', status: 'Partial' }
  ]

  const handleCancel = (order) => {
    // TODO: wire to real cancel API
    // For now provide a simple stub to indicate action
    // eslint-disable-next-line no-alert
    alert(`Cancel requested for order placed ${order.time}`)
  }

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
          <div key={i} className="grid grid-cols-8 gap-2 text-gray-200 items-center">
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
