import React, { useEffect, useState, useRef } from 'react'
import { Chart } from 'react-chartjs-2'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  TimeScale,
  Tooltip,
  Legend,
  BarElement,
  BarController,
  LinearScale as LinearScaleAlias,
} from 'chart.js'
import 'chartjs-adapter-date-fns'
import { CandlestickController, CandlestickElement } from 'chartjs-chart-financial'
import DepthChart from './DepthChart'

ChartJS.register(CategoryScale, LinearScale, LinearScaleAlias, TimeScale, Tooltip, Legend, BarElement, BarController, CandlestickController, CandlestickElement)

export default function LeftChart(){
  const [candleData, setCandleData] = useState(null)
  const [volumeData, setVolumeData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [activeView, setActiveView] = useState('price') // 'price' or 'depth'
  const liveRef = useRef(null)

  useEffect(()=>{
    let mounted = true

    async function fetchInitial(){
      try{
        // Fetch OHLC (candles) and volumes from CoinGecko
        const ohlcRes = await fetch('https://api.coingecko.com/api/v3/coins/bitcoin/ohlc?vs_currency=usd&days=1')
        const marketRes = await fetch('https://api.coingecko.com/api/v3/coins/bitcoin/market_chart?vs_currency=usd&days=1')
        const ohlcJson = await ohlcRes.json()
        const marketJson = await marketRes.json()

        if(!mounted) return

        // ohlcJson: [[ts, o, h, l, c], ...]
        const candles = ohlcJson.map(c => ({ x: c[0], o: c[1], h: c[2], l: c[3], c: c[4] }))
        // volumes: marketJson.total_volumes -> [[ts, vol], ...]
        const vols = (marketJson.total_volumes || []).map(v => ({ t: v[0], v: v[1] }))

        // match volumes to candles by nearest timestamp
        const candleVolumes = candles.map(c => {
          let best = 0
          let bestDiff = Infinity
          for(const vv of vols){
            const diff = Math.abs(vv.t - c.x)
            if(diff < bestDiff){ bestDiff = diff; best = vv.v }
          }
          return best
        })

        // style candles to be tall & slim and give wicks/borders suitable for a dark theme
        setCandleData({ datasets: [{
          label: 'Candles',
          data: candles,
          // control visual width of candles
          maxBarThickness: 10,
          barPercentage: 0.45,
          categoryPercentage: 0.6,
          // provide per-point border color so up/down bars match darker theme
          borderColor: candles.map(c => (c.c >= c.o ? '#064e3b' : '#7f1d1d')),
          borderWidth: 1
        }] })

        // volume bars colored according to candle direction (green for up, red for down)
        setVolumeData({ datasets: [{
          label: 'Volume',
          data: candles.map((c,i)=> ({ x: c.x, y: candleVolumes[i] })),
          backgroundColor: candles.map(c => (c.c >= c.o ? 'rgba(16,185,129,0.9)' : 'rgba(239,68,68,0.9)')),
          borderSkipped: false
        }] })
        setLoading(false)

        // establish websocket to Binance for real-time trade ticks (price + qty)
        let ws = null
        let reconnectAttempt = 0
        const connectWS = () => {
          try{
            ws = new WebSocket('wss://stream.binance.com:9443/ws/btcusdt@trade')
            ws.onopen = () => { reconnectAttempt = 0 }
            ws.onmessage = (ev) => {
              try{
                const msg = JSON.parse(ev.data)
                const price = Number(msg.p)
                const ts = msg.T
                const qty = msg.q ? Number(msg.q) : 0
                if(price && mounted){
                  const t = ts
                  // append/update last candle
                  setCandleData(prev => {
                    if(!prev) return prev
                    const data = [...prev.datasets[0].data]
                    const last = data[data.length-1]
                    const minute = 60 * 1000
                    if(last && Math.abs(last.x - t) < minute){
                      // update existing last candle
                      const updated = {...last}
                      updated.h = Math.max(updated.h, price)
                      updated.l = Math.min(updated.l, price)
                      updated.c = price
                      data[data.length-1] = updated
                    } else {
                      // push a new small candle
                      data.push({ x: t, o: price, h: price, l: price, c: price })
                    }
                    const maxLen = 240
                    if(data.length > maxLen) data.splice(0, data.length - maxLen)
                    return {...prev, datasets: [{...prev.datasets[0], data}]}
                  })

                  setVolumeData(prev => {
                    if(!prev) return prev
                    const data = [...prev.datasets[0].data]
                    const last = data[data.length-1]
                    const minute = 60 * 1000
                    if(last && Math.abs(last.x - ts) < minute){
                      data[data.length-1] = {...last, y: last.y + qty}
                    } else {
                      data.push({ x: ts, y: qty })
                    }
                    const maxLen = 240
                    if(data.length > maxLen) data.splice(0, data.length - maxLen)
                    return {...prev, datasets: [{...prev.datasets[0], data}]}
                  })
                }
              }catch(e){ }
            }
            ws.onclose = () => { if(!mounted) return; reconnectAttempt += 1; const delay = Math.min(30000, 1000 * (reconnectAttempt + 1)); setTimeout(()=> connectWS(), delay) }
            ws.onerror = () => { try{ ws.close() }catch(e){} }
          }catch(e){ reconnectAttempt += 1; const delay = Math.min(30000, 1000 * (reconnectAttempt + 1)); setTimeout(()=> connectWS(), delay) }
        }
        connectWS()
        liveRef.current = { close: () => { try{ ws && ws.close() }catch(e){} } }

      }catch(e){
        console.error('chart load error', e)
      }
    }

    fetchInitial()

    return ()=>{
      mounted = false
      if(liveRef.current && typeof liveRef.current.close === 'function'){
        try{ liveRef.current.close() }catch(e){}
      }
    }
  }, [])

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    elements: {
      // candlestick element styling (chartjs-chart-financial uses element id 'candlestick')
      candlestick: {
        wickColor: '#374151',
        wickWidth: 1.2,
        borderWidth: 1.2
      }
    },
    scales: {
      x: {
        type: 'time',
        time: { unit: 'minute' },
        ticks: { color: '#9CA3AF' },
        grid: { color: 'rgba(255,255,255,0.03)' }
      },
      y: {
        display: true,
        ticks: { color: '#9CA3AF' },
        position: 'right',
        grid: { color: 'rgba(255,255,255,0.03)' }
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: { mode: 'index', intersect: false }
    }
  }

  const volOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: { type: 'time', time: { unit: 'minute' }, ticks: { color: '#9CA3AF' } },
      y: { display: true, ticks: { color: '#9CA3AF' }, position: 'left' }
    },
    plugins: { legend: { display: false } }
  }

  return (
    <div className="chart-placeholder rounded-md p-4 min-h-[360px]">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <button onClick={()=>setActiveView('price')} className={`px-3 py-1 rounded ${activeView==='price' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}>Price chart</button>
          <button onClick={()=>setActiveView('depth')} className={`px-3 py-1 rounded ${activeView==='depth' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}>Depth chart</button>
        </div>
        <div className="text-sm text-gray-400">VOL 741.23</div>
      </div>

      <div className="mt-6 bg-transparent rounded-md">
        <div className="h-72">
          {loading && <div className="flex items-center justify-center h-full text-gray-400">Loading chart…</div>}
          {!loading && activeView === 'price' && candleData && (
            <Chart type="candlestick" data={candleData} options={options} />
          )}
          {!loading && activeView === 'depth' && candleData && (
            (() => {
              const last = candleData.datasets[0].data[candleData.datasets[0].data.length - 1]
              const lastPrice = last && (last.c || last.o || last.h || last.l) ? (last.c || last.o || last.h || last.l) : 1000
              return <DepthChart lastPrice={lastPrice} />
            })()
          )}
        </div>

        <div className="h-24 mt-2">
          {activeView === 'price' && !loading && volumeData && (
            <Chart type="bar" data={volumeData} options={volOptions} />
          )}
          {activeView === 'depth' && !loading && (
            <div className="text-sm text-gray-400 flex items-center justify-center h-full pt-[30px]">Depth view shows aggregated bids/asks</div>
          )}
        </div>
      </div>
    </div>
  )
}



