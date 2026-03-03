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

const nf = (n, opts) => new Intl.NumberFormat(undefined, opts).format(n || 0);

export default function DepthChart({
  lastPrice  = null,
  wsUrl      = "ws://localhost:8000/ws/orders",
  depth      = 50,
  priceGap   = 1,
}) {
  const [orders, setOrders]   = useState([]);
  const wsRef                 = useRef(null);
  const reconnectRef          = useRef(null);

  useEffect(() => {
    function connect() {
      try {
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.onopen    = () => console.debug("[DepthChart] WS connected");
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
        ws.onerror = () => ws.close();
        ws.onclose = () => {
          reconnectRef.current = setTimeout(connect, 2000);
        };
      } catch {
        reconnectRef.current = setTimeout(connect, 2000);
      }
    }
    connect();
    return () => {
      wsRef.current?.close();
      clearTimeout(reconnectRef.current);
    };
  }, [wsUrl]);

  const { data, totals, midPrice, xTicks, yTicks } = useMemo(() => {

    // ── 1. parse & filter ─────────────────────────────────────────────────────
    const parsedOrders = (orders || [])
      .filter(o =>
        o?.type === "Limit" &&
        Number(o.remaining_quantity) > 0 &&
        (o.status === "Open" || o.status === "Partial")
      )
      .map(o => ({
        price:  o.priceSats != null
                  ? parseInt(String(o.priceSats).replace(/,/g, ""), 10)
                  : null,
        amount: Number(o.remaining_quantity) || 0,
        side:   o.side,
      }))
      .filter(p => p.price > 0 && p.amount > 0);

    // ── 2. mid price from RAW unbucketed prices ───────────────────────────────
    const rawBestBid = parsedOrders
      .filter(o => o.side === "Buy")
      .reduce((best, o) => (o.price > (best ?? -Infinity) ? o.price : best), null);

    const rawBestAsk = parsedOrders
      .filter(o => o.side === "Sell")
      .reduce((best, o) => (o.price < (best ?? Infinity)  ? o.price : best), null);

    const mid =
      rawBestBid != null && rawBestAsk != null
        ? (rawBestBid + rawBestAsk) / 2
        : (lastPrice ?? rawBestBid ?? rawBestAsk ?? null);

    // ── 3. bucket by priceGap ─────────────────────────────────────────────────
    const bidMap = new Map();
    const askMap = new Map();

    for (const { price, amount, side } of parsedOrders) {
      const bucket = Math.floor(price / priceGap) * priceGap;
      if (side === "Buy") {
        bidMap.set(bucket, (bidMap.get(bucket) || 0) + amount);
      } else {
        askMap.set(bucket, (askMap.get(bucket) || 0) + amount);
      }
    }

    // bids: highest → lowest   asks: lowest → highest
    const aggBids = Array.from(bidMap.entries())
      .map(([price, amount]) => ({ price, amount }))
      .sort((a, b) => b.price - a.price);

    const aggAsks = Array.from(askMap.entries())
      .map(([price, amount]) => ({ price, amount }))
      .sort((a, b) => a.price - b.price);

    // ── 4. window ±25% around mid ─────────────────────────────────────────────
    const limitPct  = 0.25;
    const windowMin = mid ? Math.max(1, Math.floor(mid * (1 - limitPct))) : null;
    const windowMax = mid ? Math.ceil(mid * (1 + limitPct))               : null;
    const inWindow  = p  => !mid || (p >= windowMin && p <= windowMax);

    const winBids = aggBids.filter(x => inWindow(x.price));
    const winAsks = aggAsks.filter(x => inWindow(x.price));

    const useBids = winBids.length ? winBids : aggBids.slice(0, depth);
    const useAsks = winAsks.length ? winAsks : aggAsks.slice(0, depth);

    // ── 5. build unified price axis ───────────────────────────────────────────
    const allPrices = Array.from(
      new Set([...useBids.map(x => x.price), ...useAsks.map(x => x.price)])
    ).sort((a, b) => a - b);

    if (allPrices.length === 0) {
      return {
        data: [], totals: { totalBidAmount: 0, totalAskAmount: 0, totalCost: 0 },
        midPrice: mid, xTicks: [], yTicks: [0],
      };
    }

    // ── 6. cumulative curves (correct step-chart logic) ───────────────────────
    //
    // Bids  → cumulative from RIGHT to LEFT
    //   at price P: sum of all bid buckets where bucket >= P
    //   (how much you can sell at or above P)
    //
    // Asks  → cumulative from LEFT to RIGHT
    //   at price P: sum of all ask buckets where bucket <= P
    //   (how much you can buy at or below P)
    //
    // Both are pre-computed as prefix sums for O(n) instead of O(n²)

    // asks prefix (left→right)
    const askPrefix = new Map();
    let askRunning = 0;
    for (const p of allPrices) {
      const bucket = askMap.get(p);
      if (bucket) askRunning += bucket;
      askPrefix.set(p, askRunning);
    }

    // bids prefix (right→left)
    const bidPrefix = new Map();
    let bidRunning = 0;
    for (const p of [...allPrices].reverse()) {
      const bucket = bidMap.get(p);
      if (bucket) bidRunning += bucket;
      bidPrefix.set(p, bidRunning);
    }

    const dataPoints = allPrices.map(p => ({
      price: p,
      bids:  bidPrefix.get(p) || 0,
      asks:  askPrefix.get(p) || 0,
    }));

    // ── 7. x ticks (evenly spaced, snapped to priceGap) ──────────────────────
    const minP  = allPrices[0];
    const maxP  = allPrices[allPrices.length - 1];
    const xStep = Math.max(priceGap, Math.round((maxP - minP) / 7));
    const xTicksArr = [];
    for (let v = minP; v <= maxP; v += xStep) xTicksArr.push(v);
    if (xTicksArr[xTicksArr.length - 1] !== maxP) xTicksArr.push(maxP);

    // ── 8. y ticks ────────────────────────────────────────────────────────────
    const maxY  = dataPoints.reduce((m, d) => Math.max(m, d.bids, d.asks), 1);
    const exp   = Math.floor(Math.log10(Math.max(1, maxY)));
    const yStep = Math.max(1, Math.pow(10, Math.max(0, exp - 1)));
    const yTicksArr = [];
    for (let v = 0; v <= Math.ceil(maxY / yStep) * yStep; v += yStep) yTicksArr.push(v);

    return {
      data: dataPoints,
      totals: {
        totalBidAmount: useBids.reduce((s, x) => s + x.amount, 0),
        totalAskAmount: useAsks.reduce((s, x) => s + x.amount, 0),
        totalCost:
          useBids.reduce((s, x) => s + x.price * x.amount, 0) +
          useAsks.reduce((s, x) => s + x.price * x.amount, 0),
      },
      midPrice: mid,
      xTicks:   xTicksArr,
      yTicks:   yTicksArr,
    };
  }, [orders, lastPrice, priceGap, depth]);

  return (
    <div className="relative text-gray-200 min-w-0">
      <div className="flex flex-col gap-1 sm:flex-row sm:justify-between sm:items-baseline mb-2">
        <div className="text-xs sm:text-sm">
          Depth{" "}
          <span className="font-semibold text-green-400">
            {nf(totals.totalBidAmount, { maximumFractionDigits: 4 })}
          </span>
          {" / "}
          <span className="font-semibold text-red-400">
            {nf(totals.totalAskAmount, { maximumFractionDigits: 4 })}
          </span>
        </div>
        <div className="text-xs sm:text-sm">
          Total Cost{" "}
          <span className="font-semibold text-red-400">{nf(totals.totalCost)}</span>
        </div>
      </div>

      <div className="text-center text-xs text-gray-300 mb-2">
        Mid Market{" "}
        <span className="font-semibold">
          {midPrice
            ? nf(midPrice, { minimumFractionDigits: 2, maximumFractionDigits: 2 })
            : "—"}
        </span>
        {priceGap > 1 && (
          <span className="ml-2 text-yellow-400 text-xs">(gap {priceGap})</span>
        )}
      </div>

      <div className="h-48 sm:h-64 md:h-80 lg:h-[360px] min-w-0">
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
            <Area
              type="stepAfter"
              dataKey="bids"
              stroke="#10B981"
              fill="#063E30"
              fillOpacity={1}
              isAnimationActive={false}
            />
            <Area
              type="stepAfter"
              dataKey="asks"
              stroke="#EF4444"
              fill="#3B0F11"
              fillOpacity={1}
              isAnimationActive={false}
            />
            {midPrice != null && (
              <>
                <ReferenceLine
                  x={midPrice}
                  stroke="rgba(156,163,175,0.8)"
                  strokeDasharray="4 4"
                />
                <ReferenceDot
                  x={midPrice}
                  y={0}
                  r={5}
                  fill="#ffffff"
                  stroke="#111827"
                />
              </>
            )}
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}