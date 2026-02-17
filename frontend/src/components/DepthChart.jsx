import React from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
} from "recharts";

function buildRechartsDepth(lastPrice){
  const steps = 40;
  const stepSize = Math.max(1, Math.round(lastPrice * 0.0005));
  const bids = [];
  const asks = [];
  for(let i=0;i<steps;i++){
    const priceBid = Math.max(0, Math.round(lastPrice - (i+1)*stepSize));
    const priceAsk = Math.round(lastPrice + (i+1)*stepSize);
    const size = Math.max(1, Math.round((steps - i) * (1 + i/steps)));
    bids.push({ price: priceBid, size });
    asks.push({ price: priceAsk, size });
  }
  // cumulative toward mid
  bids.sort((a,b)=> a.price - b.price);
  asks.sort((a,b)=> a.price - b.price);
  let cum=0;
  const bidCum = bids.map(b => ({ price: b.price, bids: (cum += b.size) }))
  cum = 0;
  const askCum = asks.map(a => ({ price: a.price, asks: (cum += a.size) }))

  // merge price points
  const prices = Array.from(new Set([...bidCum.map(d=>d.price), lastPrice, ...askCum.map(d=>d.price)])).sort((a,b)=>a-b)
  const data = prices.map(p => {
    const left = bidCum.find(d=>d.price===p)
    const right = askCum.find(d=>d.price===p)
    return { price: p, bids: left ? left.bids : 0, asks: right ? right.asks : 0 }
  })

  // totals
  const totalBidAmount = bidCum.length ? bidCum[bidCum.length-1].bids : 0
  const totalAskAmount = askCum.length ? askCum[askCum.length-1].asks : 0
  const totalAmount = totalBidAmount + totalAskAmount
  const totalBidCost = bids.reduce((s,p)=> s + p.price * p.size, 0)
  const totalAskCost = asks.reduce((s,p)=> s + p.price * p.size, 0)
  const totalCost = totalBidCost + totalAskCost

  // compute y ticks (fixed 50 increment) and x ticks (sampled)
  const allY = data.map(d => Math.max(d.bids, d.asks))
  const maxY = Math.max(...allY, 1)
  const step = 50
  const yMax = Math.ceil(maxY / step) * step
  const yTicks = []
  for (let v = 0; v <= yMax; v += step) yTicks.push(v)

  // sample about 8 x ticks evenly
  const sample = Math.min(8, prices.length)
  const xTicks = []
  if(prices.length > 0){
    for(let i=0;i<sample;i++){
      const idx = Math.floor(i * (prices.length - 1) / (sample - 1))
      xTicks.push(prices[idx])
    }
  }

  return { data, totals: { totalAmount, totalCost }, min: prices[0], max: prices[prices.length-1], xTicks, yTicks }
}

export default function DepthChart({ lastPrice = 1000 }) {
  const { data, totals, min, max, xTicks, yTicks } = buildRechartsDepth(lastPrice)
  const fmt = v => new Intl.NumberFormat().format(v)

  return (
    <div className="relative text-gray-200">
      <div className="absolute left-2 top-2 text-sm text-white">Depth Amount <span className="font-semibold text-red-400">{totals.totalAmount ? totals.totalAmount.toFixed(3) : '0.000'}</span> BTC  Cost <span className="font-semibold text-red-400">{fmt(totals.totalCost || 0)}</span> USD</div>
      <div className="absolute left-0 right-0 text-center top-2 text-sm text-gray-200">Mid Market <span className="font-semibold">${fmt(lastPrice)}</span></div>
      <div style={{ height: 360 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 24, right: 28, left: 28, bottom: 12 }}>
            <XAxis
              dataKey="price"
              type="number"
              domain={[min, max]}
              ticks={xTicks}
              tickFormatter={(v) => new Intl.NumberFormat(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(v)}
              tick={{ fill: '#cbd5e1', fontSize: 12 }}
              axisLine={{ stroke: '#334155', strokeWidth: 1 }}
              tickLine={{ stroke: '#334155' }}
              padding={{ left: 0, right: 0 }}
              tickMargin={8}
            />
            <YAxis
              orientation="right"
              ticks={yTicks}
              tickFormatter={(v) => new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 }).format(v)}
              tick={{ fill: '#cbd5e1', fontSize: 12 }}
              axisLine={{ stroke: '#334155', strokeWidth: 1 }}
              tickLine={{ stroke: '#334155' }}
              domain={[0, 'dataMax']}
              allowDecimals={false}
              tickMargin={8}
            />
            <Tooltip formatter={(value, name) => [value, name]} labelFormatter={(v) => `Price: ${fmt(v)}`} />

            {/* left bids area */}
            <Area type="stepAfter" dataKey="bids" stroke="#10B981" fill="#063E30" fillOpacity={1} />

            {/* right asks area */}
            <Area type="stepAfter" dataKey="asks" stroke="#EF4444" fill="#3B0F11" fillOpacity={1} />

            {/* mid-market vertical line */}
            <ReferenceLine x={lastPrice} stroke="rgba(156,163,175,0.8)" strokeDasharray="4 4" />
            {/* meeting marker at bottom */}
            <ReferenceDot x={lastPrice} y={0} r={6} fill="#ffffff" stroke="#111111" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
