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

// white crosshair plugin – draws vertical line and top-of-candle horizontal
// please keep this in the file; removing it will disable the reference line
const verticalCrosshairPlugin = {
  id: 'verticalCrosshair',
  afterDraw(chart) {
    const { ctx, chartArea, scales } = chart
    const active = chart.tooltip.getActiveElements ? chart.tooltip.getActiveElements() : chart.tooltip?.active || []
    if (!active.length) return
    const { top, left, width, height } = chartArea
    const point = active[0]
    if (!point) return

    let xPos = chart.tooltip.caretX
    if (xPos === undefined) {
      xPos = point.element?.x
    }
    if (xPos === undefined) return
    if (xPos < left) xPos = left
    if (xPos > left + width) xPos = left + width

    const yScale = scales.y
    const highVal = point.raw?.h
    const yHigh = yScale ? yScale.getPixelForValue(highVal) : undefined

    ctx.save()
    ctx.strokeStyle = '#ffffff'
    ctx.lineWidth = 1.5
    ctx.setLineDash([4, 2])

    // vertical crosshair
    ctx.beginPath()
    ctx.moveTo(xPos, top)
    ctx.lineTo(xPos, top + height)
    ctx.stroke()

    // horizontal line at high
    if (yHigh !== undefined) {
      ctx.beginPath()
      ctx.moveTo(left, yHigh)
      ctx.lineTo(left + width, yHigh)
      ctx.stroke()
    }
    ctx.restore()
  }
}

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
  CandlestickElement,
  verticalCrosshairPlugin
)

const MAX_CANDLES = 240

export default function LeftChart() {
  const [candleData, setCandleData]   = useState(null)
  const [volumeData, setVolumeData]   = useState(null)
  const [loading, setLoading]         = useState(true)
  const [activeView, setActiveView]   = useState('price') // 'price' | 'depth'
  const [viewPosition, setViewPosition] = useState(100)   // 0–100: horizontal slider position
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

  // derive shared x-axis min/max from slider and available data
  const computeXRange = () => {
    if (!candleData || !candleData.datasets?.[0]?.data?.length) return {}
    const data = candleData.datasets[0].data
    const xs = data.map(d => d.x).sort((a, b) => a - b)
    const minAll = xs[0]
    const maxAll = xs[xs.length - 1]
    if (minAll === maxAll) return {}

    const totalSpan = maxAll - minAll
    const windowPercent = 30 // visible window size (% of full range)
    const clampedPos = Math.min(100, Math.max(0, viewPosition))
    const rightFrac = clampedPos / 100
    const right = minAll + totalSpan * rightFrac
    const windowSpan = (totalSpan * windowPercent) / 100
    let left = right - windowSpan
    if (left < minAll) {
      left = minAll
    }
    return { min: left, max: right }
  }

  const xRange = computeXRange()

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
        ...xRange,
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
      verticalCrosshair: {},    }, //enables the plugin
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
        ...xRange,
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
    <div className="chart-placeholder rounded-md p-3 sm:p-4 min-h-[280px] md:min-h-[320px] lg:min-h-[360px]">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={() => setActiveView('price')}
            className={`px-3 py-1 rounded text-sm ${activeView === 'price' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >
            Price chart
          </button>
          <button
            onClick={() => setActiveView('depth')}
            className={`px-3 py-1 rounded text-sm ${activeView === 'depth' ? 'bg-gray-700 text-white' : 'text-gray-400'}`}
          >
            Depth chart
          </button>
        </div>
        <div className="text-xs sm:text-sm text-gray-400">
          {lastPrice ? `Last: ${lastPrice.toLocaleString()}` : 'Waiting for trades…'}
        </div>
      </div>

      <div className="mt-4 md:mt-6 bg-transparent rounded-md">
        {/* Main chart area */}
        <div className="h-48 sm:h-56 md:h-64 lg:h-72">
          {loading && (
            <div className="flex items-center justify-center h-full text-gray-400 text-sm">
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
        <div className="h-16 sm:h-20 md:h-24 mt-2">
          {activeView === 'price' && !loading && volumeData && (
            <Chart type="bar" data={volumeData} options={volOptions} />
          )}
          {activeView === 'depth' && !loading && (
            <div className="text-xs sm:text-sm text-gray-400 flex items-center justify-center h-full">
              Depth view shows aggregated bids/asks
            </div>
          )}
        </div>

        {/* Horizontal slider for panning the time range (price view only) */}
        {activeView === 'price' && !loading && candleData && (
          <div className="mt-3">
            <input
              type="range"
              min="0"
              max="100"
              value={viewPosition}
              onChange={(e) => setViewPosition(Number(e.target.value))}
              className="w-full accent-gray-500"
            />
          </div>
        )}
      </div>
    </div>
  )
}