import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceDot,
  CartesianGrid,
} from "recharts";

// number formatter
const nf = (n, opts) => new Intl.NumberFormat(undefined, opts).format(n || 0);

// aggregate amounts by price
function aggregateByPrice(list) {
  const map = new Map();
  for (const { price, amount } of list) {
    if (!Number.isFinite(price) || amount <= 0) continue;
    map.set(price, (map.get(price) || 0) + amount);
  }
  return Array.from(map.entries()).map(([price, amount]) => ({ price, amount }));
}

export default function DepthChart({ lastPrice = null, wsUrl = "ws://localhost:8000/ws/orders", depth = 50 }) {
  const [orders, setOrders] = useState([]);
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  // WebSocket connection
  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;

        ws.onopen = () => console.debug("[DepthChart] WS connected");
        ws.onmessage = (ev) => {
          try {
            const msg = JSON.parse(ev.data);
            if (msg.type === "initial" || msg.type === "update") {
              setOrders(msg.orders || []);
            }
          } catch (err) {
            console.error("[DepthChart] parse error", err);
          }
        };
        ws.onerror = (err) => console.error("[DepthChart] WS error", err);
        ws.onclose = () => {
          console.debug("[DepthChart] WS closed, reconnecting...");
          reconnectRef.current = setTimeout(connect, 2000);
        };
      } catch (err) {
        console.error("[DepthChart] WS connect failed", err);
        reconnectRef.current = setTimeout(connect, 2000);
      }
    }
    connect();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
  }, [wsUrl]);

  // compute chart data
  const { data, totals, midPrice, xTicks, yTicks } = useMemo(() => {
    const limitPct = 0.25; // +/- window fraction

    // parse & filter orders
    const parsedOrders = (orders || [])
      .filter(
        (o) =>
          o &&
          o.type === "Limit" &&
          Number(o.remaining_quantity) > 0 &&
          (o.status === "Open" || o.status === "Partial")
      )
      .map((o) => {
        const price =
          o.priceSats != null ? parseInt(String(o.priceSats).replace(/,/g, ""), 10) : null;
        return { price, amount: Number(o.remaining_quantity) || 0, side: o.side };
      })
      .filter((p) => p.price > 0 && p.amount > 0);

    // aggregate by exact price first
    const bidsByPrice = aggregateByPrice(parsedOrders.filter((p) => p.side === "Buy").map(p => ({ price: p.price, amount: p.amount })));
    const asksByPrice = aggregateByPrice(parsedOrders.filter((p) => p.side === "Sell").map(p => ({ price: p.price, amount: p.amount })));
    // sort
    const aggBids = bidsByPrice.sort((a, b) => b.price - a.price);
    const aggAsks = asksByPrice.sort((a, b) => a.price - b.price);

    // compute best bid/ask and mid (prefer best bid/ask; fallback to lastPrice)
    const bestBid = aggBids.length ? aggBids[0].price : null;
    const bestAsk = aggAsks.length ? aggAsks[0].price : null;
    const computedMid =
      bestBid != null && bestAsk != null ? (bestBid + bestAsk) / 2 : (lastPrice ?? bestBid ?? bestAsk ?? null);

    // windowing around mid if available
    const mid = computedMid != null ? Number(computedMid) : null;
    let windowMin = null;
    let windowMax = null;
    if (mid) {
      windowMin = Math.max(1, Math.floor(mid * (1 - limitPct)));
      windowMax = Math.ceil(mid * (1 + limitPct));
    }

    // dynamic bucket sizing to avoid extremely dense X axis
    const bucketSize = mid ? Math.max(1, Math.round(mid * 0.001)) : 1;

    // bucket and aggregate into map {price -> {price, bid, ask}}
    const mapAgg = new Map();
    for (const { price, amount, side } of parsedOrders) {
      if (price == null) continue;
      if (mid && (price < windowMin || price > windowMax)) continue; // apply window
      const bucketPrice = Math.round(price / bucketSize) * bucketSize;
      const key = bucketPrice;
      const entry = mapAgg.get(key) || { price: key, bid: 0, ask: 0 };
      if (side === "Buy") entry.bid += amount;
      else entry.ask += amount;
      mapAgg.set(key, entry);
    }

    const aggList = Array.from(mapAgg.values());
    const finalBids = aggList
      .filter((x) => x.bid > 0)
      .map((x) => ({ price: x.price, amount: x.bid }))
      .sort((a, b) => b.price - a.price);
    const finalAsks = aggList
      .filter((x) => x.ask > 0)
      .map((x) => ({ price: x.price, amount: x.ask }))
      .sort((a, b) => a.price - b.price);

    // build price list (ascending)
    let prices = Array.from(new Set([...finalAsks.map((a) => a.price), ...finalBids.map((b) => b.price)]));
    prices.sort((a, b) => a - b);

    // fallback: if window filtered everything, include top N of each side (no window)
    if (prices.length === 0) {
      const fallbackBids = bidsByPrice.sort((a,b)=>b.price-a.price).slice(0, depth).map(x=>x.price);
      const fallbackAsks = asksByPrice.sort((a,b)=>a.price-b.price).slice(0, depth).map(x=>x.price);
      prices = Array.from(new Set([...fallbackAsks, ...fallbackBids])).sort((a,b)=>a-b);
    }

    // ensure data is dense enough but not excessively so: generate evenly spaced xTicks across min/max
    const minPrice = prices.length ? prices[0] : (mid || 0);
    const maxPrice = prices.length ? prices[prices.length - 1] : (mid || 0);
    const priceRange = Math.max(1, maxPrice - minPrice);
    const sampleCount = Math.min(8, Math.max(2, Math.floor(prices.length / Math.ceil(bucketSize / Math.max(1, Math.round(mid ? mid/100000 : 1))))));

    // create xTicks as linear samples across range (guarantees evenly spaced axis)
    const xTicksArr = [];
    const ticks = Math.min(8, Math.max(2, Math.ceil(prices.length / Math.max(1, Math.floor(prices.length / 8)))));
    const step = Math.max(1, Math.floor(priceRange / (ticks - 1 || 1)));
    for (let v = minPrice; v <= maxPrice; v += step) xTicksArr.push(v);
    // ensure last tick is maxPrice
    if (xTicksArr[xTicksArr.length - 1] !== maxPrice) xTicksArr.push(maxPrice);

    // cumulative helpers
    function cumBidAt(p) {
      let s = 0;
      for (const it of finalBids) if (it.price >= p) s += it.amount;
      return s;
    }
    function cumAskAt(p) {
      let s = 0;
      for (const it of finalAsks) if (it.price <= p) s += it.amount;
      return s;
    }

    // build data points by using the explicit prices array (keeps ordering consistent)
    const dataPoints = prices.map((p) => ({ price: p, bids: cumBidAt(p), asks: cumAskAt(p) }));

    // totals & y ticks
    const totalBidAmount = finalBids.reduce((s, x) => s + x.amount, 0);
    const totalAskAmount = finalAsks.reduce((s, x) => s + x.amount, 0);
    const totalCost =
      finalBids.reduce((s, x) => s + x.price * x.amount, 0) + finalAsks.reduce((s, x) => s + x.price * x.amount, 0);

    const maxY = dataPoints.reduce((m, d) => Math.max(m, d.bids, d.asks), 1);
    const exponent = Math.floor(Math.log10(Math.max(1, maxY)));
    const yStep = Math.max(1, Math.pow(10, Math.max(0, exponent - 1)));
    const yTicksArr = [];
    for (let v = 0; v <= Math.ceil(maxY / yStep) * yStep; v += yStep) yTicksArr.push(v);

    return {
      data: dataPoints,
      totals: { totalBidAmount, totalAskAmount, totalCost },
      midPrice: mid,
      xTicks: xTicksArr,
      yTicks: yTicksArr,
    };
  }, [orders, lastPrice, depth]);

  return (
    <div className="relative text-gray-200">
      {/* Header */}
      <div className="flex justify-between items-baseline mb-2">
        <div className="text-sm">
          Depth{" "}
          <span className="font-semibold text-green-400">{nf(totals.totalBidAmount, { maximumFractionDigits: 4 })}</span>{" "}
          /{" "}
          <span className="font-semibold text-red-400">{nf(totals.totalAskAmount, { maximumFractionDigits: 4 })}</span>
        </div>
        <div className="text-sm">
          Total Cost <span className="font-semibold text-red-400">{nf(totals.totalCost)}</span>
        </div>
      </div>

      <div className="text-center text-xs text-gray-300 mb-2">
        Mid Market{" "}
        <span className="font-semibold">
          {midPrice ? nf(midPrice, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : "—"}
        </span>
      </div>

      {/* Chart */}
      <div style={{ height: 360 }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={data} margin={{ top: 8, right: 36, left: 8, bottom: 24 }}>
            <CartesianGrid stroke="#1f2937" strokeDasharray="3 3" />
            <XAxis
              dataKey="price"
              type="number"
              domain={["dataMin", "dataMax"]}
              ticks={xTicks}
              tickFormatter={(v) => nf(v, { minimumFractionDigits: 0 })}
              tick={{ fill: "#cbd5e1", fontSize: 12 }}
              axisLine={{ stroke: "#334155", strokeWidth: 1 }}
              tickLine={{ stroke: "#334155" }}
            />
            <YAxis
              orientation="right"
              ticks={yTicks}
              tickFormatter={(v) => nf(v, { maximumFractionDigits: 0 })}
              tick={{ fill: "#cbd5e1", fontSize: 12 }}
              axisLine={{ stroke: "#334155", strokeWidth: 1 }}
              tickLine={{ stroke: "#334155" }}
              domain={[0, "dataMax"]}
              allowDecimals={false}
            />
            <Tooltip
              formatter={(value, name) => [
                nf(value, { maximumFractionDigits: 8 }),
                name === "bids" ? "Bids (cum)" : "Asks (cum)",
              ]}
              labelFormatter={(v) => `Price: ${nf(v, { maximumFractionDigits: 0 })}`}
            />
            <Area type="stepAfter" dataKey="bids" stroke="#10B981" fill="#063E30" fillOpacity={1} />
            <Area type="stepAfter" dataKey="asks" stroke="#EF4444" fill="#3B0F11" fillOpacity={1} />
            {midPrice != null && (
              <>
                <ReferenceLine x={midPrice} stroke="rgba(156,163,175,0.8)" strokeDasharray="4 4" />
                <ReferenceDot x={midPrice} y={0} r={5} fill="#ffffff" stroke="#111827" />
              </>
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
