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

ChartJS.register(
  CategoryScale,
  LinearScale,
  LinearScaleAlias,
  TimeScale,
  Tooltip,
  Legend,
  BarElement,
  BarController,
  CandlestickController,
  CandlestickElement
)

const MAX_CANDLES = 240

export default function LeftChart() {
  const [candleData, setCandleData]   = useState(null)
  const [volumeData, setVolumeData]   = useState(null)
  const [loading, setLoading]         = useState(true)
  const [activeView, setActiveView]   = useState('price') // 'price' | 'depth'
  const wsRef       = useRef(null)
  const reconnectRef = useRef(null)

  useEffect(() => {
    connectWebSocket()
    return () => {
      if (wsRef.current)    wsRef.current.close()
      if (reconnectRef.current) clearTimeout(reconnectRef.current)
    }
  }, [])

  function buildChartDatasets(candles) {
    // candles: [{time, open, high, low, close, volume}, ...]
    const candleDs = candles.map(c => ({
      x: new Date(c.time).getTime(),
      o: c.open,
      h: c.high,
      l: c.low,
      c: c.close,
    }))
    const volDs = candles.map(c => ({
      x: new Date(c.time).getTime(),
      y: c.volume,
    }))
    const candleColors = candles.map(c =>
      c.close >= c.open ? '#064e3b' : '#7f1d1d'
    )
    const volColors = candles.map(c =>
      c.close >= c.open ? 'rgba(16,185,129,0.9)' : 'rgba(239,68,68,0.9)'
    )

    setCandleData({
      datasets: [{
        label: 'Candles',
        data: candleDs,
        maxBarThickness: 10,
        barPercentage: 0.45,
        categoryPercentage: 0.6,
        borderColor: candleColors,
        borderWidth: 1,
      }]
    })
    setVolumeData({
      datasets: [{
        label: 'Volume',
        data: volDs,
        backgroundColor: volColors,
        borderSkipped: false,
      }]
    })
  }

  function applyUpdate(candle) {
    const ts = new Date(candle.time).getTime()

    setCandleData(prev => {
      if (!prev) return prev
      const data = [...prev.datasets[0].data]
      const last = data[data.length - 1]
      const isGreen = candle.close >= candle.open
      const borderColor = [...(prev.datasets[0].borderColor || [])]

      if (last && last.x === ts) {
        // mutate current candle in place
        data[data.length - 1] = { x: ts, o: candle.open, h: candle.high, l: candle.low, c: candle.close }
        borderColor[borderColor.length - 1] = isGreen ? '#064e3b' : '#7f1d1d'
      } else {
        // new candle
        data.push({ x: ts, o: candle.open, h: candle.high, l: candle.low, c: candle.close })
        borderColor.push(isGreen ? '#064e3b' : '#7f1d1d')
        if (data.length > MAX_CANDLES) { data.splice(0, data.length - MAX_CANDLES); borderColor.splice(0, borderColor.length - MAX_CANDLES) }
      }
      return { ...prev, datasets: [{ ...prev.datasets[0], data, borderColor }] }
    })

    setVolumeData(prev => {
      if (!prev) return prev
      const data = [...prev.datasets[0].data]
      const bg   = [...(prev.datasets[0].backgroundColor || [])]
      const last = data[data.length - 1]
      const color = candle.close >= candle.open ? 'rgba(16,185,129,0.9)' : 'rgba(239,68,68,0.9)'

      if (last && last.x === ts) {
        data[data.length - 1] = { x: ts, y: candle.volume }
        bg[bg.length - 1] = color
      } else {
        data.push({ x: ts, y: candle.volume })
        bg.push(color)
        if (data.length > MAX_CANDLES) { data.splice(0, data.length - MAX_CANDLES); bg.splice(0, bg.length - MAX_CANDLES) }
      }
      return { ...prev, datasets: [{ ...prev.datasets[0], data, backgroundColor: bg }] }
    })
  }

  function connectWebSocket() {
    const wsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
    try {
      const ws = new WebSocket(`${wsUrl}/ws/candles`)
      wsRef.current = ws

      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data)

          if (msg.type === 'initial') {
            const candles = msg.candles || []
            if (candles.length) {
              buildChartDatasets(candles)
              setLoading(false)
            }
          }

          if (msg.type === 'candle_update') {
            applyUpdate(msg.candle)
            setLoading(false)
          }

          if (msg.type === 'candle_close') {
            // candle_close just signals the window rolled;
            // candle_update will follow immediately with the new candle.
            console.debug('[LeftChart] candle closed:', msg.candle?.time)
          }
        } catch (e) {
          // ignore parse errors
        }
      }

      ws.onerror = () => ws.close()
      ws.onclose = () => {
        reconnectRef.current = setTimeout(connectWebSocket, 2000)
      }
    } catch (e) {
      reconnectRef.current = setTimeout(connectWebSocket, 2000)
    }
  }

  // last close price for DepthChart midPrice prop
  const lastPrice = (() => {
    if (!candleData) return null
    const data = candleData.datasets[0].data
    const last = data[data.length - 1]
    return last ? last.c : null
  })()

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    elements: {
      candlestick: {
        wickColor: '#374151',
        wickWidth: 1.2,
        borderWidth: 1.2,
      }
    },
    scales: {
      x: {
        type: 'time',
        time: { unit: 'second', displayFormats: { second: 'HH:mm:ss' } },
        ticks: { color: '#9CA3AF', maxTicksLimit: 8 },
        grid: { color: 'rgba(255,255,255,0.03)' },
      },
      y: {
        display: true,
        ticks: { color: '#9CA3AF' },
        position: 'right',
        grid: { color: 'rgba(255,255,255,0.03)' },
      }
    },
    plugins: {
      legend: { display: false },
      tooltip: { mode: 'index', intersect: false },
    },
    animation: false,
  }

  const volOptions = {
    responsive: true,
    maintainAspectRatio: false,
    scales: {
      x: {
        type: 'time',
        time: { unit: 'second', displayFormats: { second: 'HH:mm:ss' } },
        ticks: { color: '#9CA3AF', maxTicksLimit: 8 },
      },
      y: {
        display: true,
        ticks: { color: '#9CA3AF' },
        position: 'left',
      }
    },
    plugins: { legend: { display: false } },
    animation: false,
  }

  return (
    <div className="chart-placeholder rounded-md p-4 min-h-[360px]">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <button
            onClick={() => setActiveView('price')}
            className={`px-3 py-1 rounded ${activeView === 'price' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >
            Price chart
          </button>
          <button
            onClick={() => setActiveView('depth')}
            className={`px-3 py-1 rounded ${activeView === 'depth' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >
            Depth chart
          </button>
        </div>
        <div className="text-sm text-gray-400">
          {lastPrice ? `Last: ${lastPrice.toLocaleString()}` : 'Waiting for trades…'}
        </div>
      </div>

      <div className="mt-6 bg-transparent rounded-md">
        {/* Main chart area */}
        <div className="h-72">
          {loading && (
            <div className="flex items-center justify-center h-full text-gray-400">
              Waiting for trades…
            </div>
          )}

          {/* Price chart (candlestick) */}
          {!loading && activeView === 'price' && candleData && (
            <Chart type="candlestick" data={candleData} options={options} />
          )}

          {/* Depth chart */}
          {!loading && activeView === 'depth' && (
            <DepthChart lastPrice={lastPrice} />
          )}
        </div>

        {/* Volume bar sub-chart */}
        <div className="h-24 mt-2">
          {activeView === 'price' && !loading && volumeData && (
            <Chart type="bar" data={volumeData} options={volOptions} />
          )}
          {activeView === 'depth' && !loading && (
            <div className="text-sm text-gray-400 flex items-center justify-center h-full">
              Depth view shows aggregated bids/asks
            </div>
          )}
        </div>
      </div>
    </div>
  )
}