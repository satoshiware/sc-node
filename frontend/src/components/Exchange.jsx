import React, { useEffect, useState, useRef } from 'react'
import { FiChevronLeft } from 'react-icons/fi'
import MarketSelect from './MarketSelect'
import LeftChart from './LeftChart'
import OrderBook from './OrderBook'
import TradeHistory from './TradeHistory'
import BuyPanel from './BuyPanel'

function fakeOrderbook(mid){
	const bids = []
	const asks = []
	for(let i=1;i<=8;i++){
		bids.push({ price: Math.max(1, Math.round((mid - i*50))), size: (Math.random()*2).toFixed(6) })
		asks.push({ price: Math.round(mid + i*50), size: (Math.random()*2).toFixed(6) })
	}
	return { bids, asks }
}

export default function Exchange({ setView }){
	const [price, setPrice] = useState(89406)
	const [change, setChange] = useState(0)
	const [orderbook, setOrderbook] = useState(() => fakeOrderbook(price))
	const [orders, setOrders] = useState([])
	const [trades, setTrades] = useState([])
	const mounted = useRef(true)

	useEffect(()=>{
		mounted.current = true
		const iv = setInterval(()=>{
			setPrice(p=>{
				const delta = (Math.random()-0.5)*200
				const next = Math.max(1, Math.round(p + delta))
				setOrderbook(fakeOrderbook(next))
				setChange(Math.round((next - p)*100)/100)
				return next
			})
		}, 1000)

		return ()=>{ mounted.current = false; clearInterval(iv) }
	}, [])

	const placeOrder = ({ side, type, price: oPrice, amount }) => {
		const id = Date.now()
		const newOrder = { id, side, type, price: oPrice, amount, status: type === 'market' ? 'Filled' : 'Open', time: new Date().toLocaleString() }
		setOrders(prev => [newOrder, ...prev])

		if(type === 'market'){
			// create trade
			setTrades(prev => [{ time: new Date().toLocaleString(), side, price: price, amount }, ...prev])
		}
	}

	const cancelOrder = (id) => {
		setOrders(prev => prev.map(o => o.id === id ? { ...o, status: 'Cancelled' } : o))
	}

	return (
		<div className="min-h-screen p-2 sm:p-4">
			<div className="sticky top-0 z-30 bg-gray-900/60 backdrop-blur-sm px-3 py-2 rounded-b-md mb-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
				<div className="flex items-center gap-3">
					<button
						type="button"
						onClick={() => setView && setView('home')}
						className="text-sm text-gray-200 hover:text-white flex items-center gap-2"
					>
						<FiChevronLeft className="w-4 h-4" />
						Back
					</button>

					<MarketSelect />
				</div>

				<div className="flex flex-wrap items-baseline gap-2 md:gap-6">
					<div className="text-xs text-gray-400">Last Price (24H)</div>
					<div className="text-lg sm:text-xl font-semibold">${price.toLocaleString()} <span className={change>=0 ? 'text-green-400 text-sm' : 'text-red-400 text-sm'}>{change>=0? `+${change}`: change}</span></div>
				</div>
			</div>

			<div className="mt-4 grid grid-cols-1 gap-4 md:grid-cols-12 lg:gap-4 xl:gap-4">
				<div className="flex flex-col gap-4 md:col-span-8 xl:col-span-8">
					<LeftChart />

					<div className="bg-gray-800 p-3 rounded-md">
						<div className="flex items-center justify-between mb-2">
							<div className="text-sm font-medium">Open Orders</div>
						</div>

						<div className="text-xs text-gray-400 grid grid-cols-4 sm:grid-cols-6 gap-1 sm:gap-2 border-b border-gray-700 pb-2 min-w-[360px] sm:min-w-0">
							<div>Time</div>
							<div>Type</div>
							<div>Side</div>
							<div>Price</div>
							<div className="hidden sm:block">Amount</div>
							<div className="text-right">Actions</div>
						</div>

						<div className="mt-2 space-y-2 text-xs sm:text-sm text-gray-200 overflow-x-auto">
							{orders.length === 0 ? (
								<div className="text-gray-500 p-6 text-center">No orders</div>
							) : (
								orders.map(o => (
									<div key={o.id} className="grid grid-cols-4 sm:grid-cols-6 gap-1 sm:gap-2 items-center min-w-[360px] sm:min-w-0">
										<div className="text-xs text-gray-200 truncate">{o.time}</div>
										<div className="truncate">{o.type}</div>
										<div className={o.side === 'Buy' ? 'text-green-300' : 'text-red-300'}>{o.side}</div>
										<div className="truncate">{o.price}</div>
										<div className="hidden sm:block truncate">{o.amount}</div>
										<div className="text-right">
											{o.status === 'Open' ? (
												<button onClick={() => cancelOrder(o.id)} className="text-sm text-red-400 hover:underline">Cancel</button>
											) : (
												<span className="text-gray-500 text-xs">{o.status}</span>
											)}
										</div>
									</div>
								))
							)}
						</div>
					</div>
				</div>

				<div className="flex flex-col gap-4 md:col-span-4 xl:col-span-4">
					<div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-2">
						<div className="min-w-0">
							<div className="bg-gray-800 p-3 rounded-md">
								<div className="text-sm font-medium mb-2">Order Book</div>
								<div className="grid grid-cols-2 text-xs text-gray-400 mb-2">
									<div className="text-left">Bids</div>
									<div className="text-right">Asks</div>
								</div>
								<div className="flex gap-2 min-w-0">
									<div className="flex-1 max-h-40 sm:max-h-48 md:max-h-56 overflow-y-auto pr-2 min-w-0">
										{orderbook.bids.map((b,i)=> (
											<div key={i} className="flex items-center justify-between text-xs sm:text-sm text-green-300 py-1 truncate">{b.size} <span className="text-gray-300">{b.price}</span></div>
										))}
									</div>
									<div className="flex-1 max-h-40 sm:max-h-48 md:max-h-56 overflow-y-auto border-l border-gray-700 pl-2 min-w-0">
										{orderbook.asks.map((a,i)=> (
											<div key={i} className="flex items-center justify-between text-xs sm:text-sm text-red-300 py-1 truncate"><span className="text-gray-300">{a.price}</span> {a.size}</div>
										))}
									</div>
								</div>
							</div>
						</div>

						<div className="min-w-0">
							<div className="bg-gray-800 p-3 rounded-md">
								<div className="text-sm font-medium mb-2">Trade history</div>
								<div className="space-y-2 text-xs sm:text-sm text-gray-300 max-h-40 sm:max-h-48 md:max-h-56 overflow-y-auto pr-2">
									{trades.length === 0 ? (
										<div className="text-gray-500">No trades</div>
									) : trades.map((t,i)=> (
										<div key={i} className="flex items-center justify-between gap-2 border-b border-gray-800 pb-1 flex-wrap">
											<div className="text-xs text-gray-400">{t.time}</div>
											<div className={t.side === 'Buy' ? 'text-green-300' : 'text-red-300'}>{t.side}</div>
											<div className="text-sm truncate">{t.amount} @ {t.price}</div>
										</div>
									))}
								</div>
							</div>
						</div>
					</div>

					<div className="min-w-0">
						<BuyPanel />
					</div>
				</div>
			</div>
		</div>
	)
}
