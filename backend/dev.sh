#!/bin/bash
set -e

DB="db/exchange.db"

echo "🧹 Cleaning database..."
sqlite3 "$DB" "DELETE FROM trades;"
sqlite3 "$DB" "DELETE FROM orders;"

echo "🚀 Starting backend services..."

cd src

# Start API
uvicorn api:app --host 0.0.0.0 --port 8000 &
API_PID=$!

sleep 1

# Start matcher
python3 matcher.py &
MATCHER_PID=$!

sleep 1
python3 bots.py

echo ""
echo "✅ Backend running"
echo "API PID: $API_PID"
echo "Matcher PID: $MATCHER_PID"
echo ""
echo "🛑 Press Ctrl+C to stop everything"

trap "echo '🛑 Stopping...'; kill $API_PID $MATCHER_PID; exit" INT

wait
