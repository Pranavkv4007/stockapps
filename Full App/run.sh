#!/bin/bash
echo "============================================"
echo "  Stock Analysis Hub - Starting..."
echo "============================================"

cd "$(dirname "$0")"

echo "Installing Python dependencies..."
pip install -r backend/requirements.txt --quiet

echo ""
echo "Starting server..."
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload &
SERVER_PID=$!

sleep 2
echo "Stock Analysis Hub running at http://localhost:8000"

# Try to open browser
if command -v xdg-open &> /dev/null; then
    xdg-open http://localhost:8000
elif command -v open &> /dev/null; then
    open http://localhost:8000
fi

wait $SERVER_PID
