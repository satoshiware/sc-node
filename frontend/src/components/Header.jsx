import React, { useEffect, useState, useRef } from "react";

const nf = (n, opts) => new Intl.NumberFormat(undefined, opts).format(n ?? 0);

export default function Header() {
  const [stats, setStats] = useState({});
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  useEffect(() => {
    connectWS();
    return () => {
      if (wsRef.current) wsRef.current.close();
      if (reconnectRef.current) clearTimeout(reconnectRef.current);
    };
    // eslint-disable-next-line
  }, []);

  function connectWS() {
    const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
    const ws = new WebSocket(`${wsUrl}/ws/market_stats`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "market_stats") setStats(data.stats || {});
      } catch (e) {
        // ignore
      }
    };

    ws.onerror = () => ws.close();
    ws.onclose = () => {
      reconnectRef.current = setTimeout(connectWS, 3000);
    };
  }

  return (
    <header className="bg-gray-900 text-gray-100 px-4 py-2 flex flex-wrap items-center gap-6 shadow">
      <div className="text-lg font-bold tracking-wide">CoinBot Exchange</div>
      <div className="flex flex-wrap gap-4 text-sm">
        <div>
          <span className="text-gray-400">Last Price:</span>{" "}
          <span className="font-semibold text-green-400">{stats.last_price ? nf(stats.last_price, { maximumFractionDigits: 2 }) : "—"}</span>
        </div>
        <div>
          <span className="text-gray-400">24h Volume:</span>{" "}
          <span className="font-semibold">{stats.volume_24h ? nf(stats.volume_24h, { maximumFractionDigits: 4 }) : "—"}</span>
        </div>
        <div>
          <span className="text-gray-400">24h High:</span>{" "}
          <span className="font-semibold text-green-300">{stats.high_24h ? nf(stats.high_24h, { maximumFractionDigits: 2 }) : "—"}</span>
        </div>
        <div>
          <span className="text-gray-400">24h Low:</span>{" "}
          <span className="font-semibold text-red-300">{stats.low_24h ? nf(stats.low_24h, { maximumFractionDigits: 2 }) : "—"}</span>
        </div>
        {/* Add more stats as needed */}
      </div>
    </header>
  );
}