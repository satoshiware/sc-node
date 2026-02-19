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
    const limitOrders = (orders || []).filter(
      (o) =>
        o &&
        o.type === "Limit" &&
        Number(o.remaining_quantity) > 0 &&
        (o.status === "Open" || o.status === "Partial")
    );

    const parsed = limitOrders
      .map((o) => {
        const price = o.priceSats != null ? Number(o.priceSats) : null;
        const amount = Number(o.remaining_quantity) || 0;
        const side = o.side;
        return { price, amount, side };
      })
      .filter((p) => p.price != null && p.amount > 0);

    const bidsRaw = parsed.filter((p) => p.side === "Buy");
    const asksRaw = parsed.filter((p) => p.side === "Sell");

    const aggBids = aggregateByPrice(bidsRaw).sort((a, b) => b.price - a.price);
    const aggAsks = aggregateByPrice(asksRaw).sort((a, b) => a.price - b.price);

    // cumulative sums
    let cum = 0;
    const bidsCum = aggBids
      .map((b) => ({ ...b, cumulative: (cum += b.amount) }))
      .slice(0, depth);
    cum = 0;
    const asksCum = aggAsks
      .map((a) => ({ ...a, cumulative: (cum += a.amount) }))
      .slice(0, depth);

    // merge for Recharts
    const chartData = [
      ...bidsCum
        .map((b) => ({ price: b.price, bids: b.cumulative, asks: 0 }))
        .reverse(), // so lowest bid is leftmost
      ...asksCum.map((a) => ({ price: a.price, bids: 0, asks: a.cumulative })),
    ];

    const totalBidAmount = bidsCum.length ? bidsCum[bidsCum.length - 1].cumulative : 0;
    const totalAskAmount = asksCum.length ? asksCum[asksCum.length - 1].cumulative : 0;
    const totalBidCost = bidsCum.reduce((s, x) => s + x.price * x.amount, 0);
    const totalAskCost = asksCum.reduce((s, x) => s + x.price * x.amount, 0);

    const bestBid = aggBids.length ? aggBids[0].price : null;
    const bestAsk = aggAsks.length ? aggAsks[0].price : null;
    const midPrice =
      bestBid != null && bestAsk != null
        ? (bestBid + bestAsk) / 2
        : lastPrice ?? (bestBid ?? bestAsk);

    // y-axis ticks
    const maxY = chartData.reduce((m, d) => Math.max(m, d.bids, d.asks), 1);
    const exponent = Math.floor(Math.log10(Math.max(1, maxY)));
    const yStep = Math.max(1, Math.pow(10, Math.max(0, exponent - 1)));
    const yTicks = [];
    for (let v = 0; v <= Math.ceil(maxY / yStep) * yStep; v += yStep) yTicks.push(v);

    // x-axis sample
    const prices = chartData.map((d) => d.price);
    const sample = Math.min(8, prices.length || 1);
    const xTicks = [];
    if (prices.length > 0) {
      for (let i = 0; i < sample; i++) {
        const idx = Math.floor(i * (prices.length - 1) / (sample - 1 || 1));
        xTicks.push(prices[idx]);
      }
    }

    return {
      data: chartData,
      totals: { totalBidAmount, totalAskAmount, totalCost: totalBidCost + totalAskCost },
      midPrice,
      xTicks,
      yTicks,
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
