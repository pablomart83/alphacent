#!/bin/bash

echo "=========================================="
echo "Restarting AlphaCent Backend Server"
echo "=========================================="

# Stop the current server
echo "Stopping current server..."
pkill -f "uvicorn src.api.app:app"
sleep 2

# Check if stopped
if pgrep -f "uvicorn src.api.app:app" > /dev/null; then
    echo "❌ Server still running, force killing..."
    pkill -9 -f "uvicorn src.api.app:app"
    sleep 1
fi

echo "✅ Server stopped"

# Start the server
echo "Starting server with new code..."
source venv/bin/activate
nohup python -m uvicorn src.api.app:app --reload --log-level debug > server.log 2>&1 &

sleep 3

# Check if started
if pgrep -f "uvicorn src.api.app:app" > /dev/null; then
    echo "✅ Server started successfully"
    echo ""
    echo "Server is running at: http://localhost:8000"
    echo "Logs: tail -f server.log"
else
    echo "❌ Failed to start server"
    echo "Check server.log for errors"
fi

echo "=========================================="
