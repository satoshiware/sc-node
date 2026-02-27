import React, { useEffect, useState, useRef } from "react";
import MarketSelect from './MarketSelect'
import Profile from './Profile'

const nf = (n, opts) => new Intl.NumberFormat(undefined, opts).format(n ?? 0);

export default function Header({ setView }) {
  const [stats, setStats] = useState({});
  const wsRef = useRef(null);
  const reconnectRef = useRef(null);

  useEffect(() => {
    connectWS();
    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectRef.current) {
        clearTimeout(reconnectRef.current);
      }
    };
  }, []);

  function connectWS() {
    try {
      const wsUrl = import.meta.env.VITE_WS_URL || "ws://localhost:8000";
      const ws = new WebSocket(`${wsUrl}/ws/market_stats`);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[Header] WebSocket connected');
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          if (data.type === "market_stats") {
            setStats(data.stats || {});
          }
        } catch (e) {
          console.error('[Header] Parse error:', e);
        }
      };

      ws.onerror = (error) => {
        console.error('[Header] WebSocket error:', error);
        ws.close();
      };

      ws.onclose = () => {
        console.log('[Header] WebSocket closed, reconnecting...');
        reconnectRef.current = setTimeout(connectWS, 3000);
      };
    } catch (err) {
      console.error('[Header] Connection error:', err);
    }
  }

  // Format change percent
  let change = stats.change_pct_24h ?? stats.change_24h ?? null;
  let changeStr = "";
  let changeColor = "";
  if (change !== null && !isNaN(change)) {
    const absChange = Math.abs(change).toFixed(2);
    if (change > 0) {
      changeStr = `(+${absChange}%)`;
      changeColor = "text-green-400";
    } else if (change < 0) {
      changeStr = `(-${absChange}%)`;
      changeColor = "text-red-400";
    } else {
      changeStr = "(0.00%)";
      changeColor = "text-gray-300";
    }
  }

  return (
    <header className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between w-full sticky top-0 z-20 bg-gray-900/50 backdrop-blur-sm px-3 py-3 sm:px-4 border-b border-gray-700">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:gap-6 md:flex-wrap">
        <MarketSelect />

        <div className="flex items-baseline gap-3">
          <div className="text-xs text-gray-400">Last Price (24H)</div>
          <div className="text-base sm:text-lg font-semibold text-white">
            ${stats.last_price ? nf(stats.last_price, { maximumFractionDigits: 2 }) : "0.00"}
            {changeStr && (
              <span className={`${changeColor} text-sm ml-2`}>{changeStr}</span>
            )}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-4 md:gap-6 text-sm text-gray-400">
          <div>
            <div className="text-xs text-gray-400">24H Volume</div>
            <div className="text-sm text-gray-200">${stats.volume_24h ? nf(stats.volume_24h, { maximumFractionDigits: 2 }) : "0.00"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">24H High</div>
            <div className="text-sm text-gray-200">${stats.high_24h ? nf(stats.high_24h, { maximumFractionDigits: 2 }) : "0.00"}</div>
          </div>
          <div>
            <div className="text-xs text-gray-400">24H Low</div>
            <div className="text-sm text-gray-200">${stats.low_24h ? nf(stats.low_24h, { maximumFractionDigits: 2 }) : "0.00"}</div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 md:justify-end md:gap-6">
        <nav className="flex flex-wrap items-center gap-3 md:gap-6">
          <button
            type="button"
            onClick={() => {
              console.log('[Header] Going to exchange');
              setView('exchange');
            }}
            className="text-sm text-gray-400 hover:text-white transition-colors cursor-pointer"
          >
            Exchange
          </button>
          <button
            type="button"
            onClick={() => {
              console.log('[Header] Going to wallet');
              setView('wallet');
            }}
            className="text-sm text-gray-400 hover:text-white transition-colors cursor-pointer"
          >
            Wallet
          </button>
          <button
            type="button"
            onClick={() => {
              console.log('[Header] Going to orders');
              setView('orders');
            }}
            className="text-sm text-gray-400 hover:text-white transition-colors cursor-pointer"
          >
            Orders
          </button>
        </nav>

        <Profile />
      </div>
    </header>
  );
}