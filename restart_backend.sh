#!/bin/bash

# Restart Backend Script

echo "🔄 Restarting AlphaCent backend..."

# Activate virtual environment if it exists
if [ -d "venv" ]; then
    echo "🐍 Activating virtual environment..."
    source venv/bin/activate
fi

# Find and kill the existing backend process
PID=$(ps aux | grep "python.*src.main" | grep -v grep | awk '{print $2}')

if [ -n "$PID" ]; then
    echo "📍 Found backend process (PID: $PID)"
    echo "🛑 Stopping backend..."
    kill $PID
    sleep 2
    
    # Force kill if still running
    if ps -p $PID > /dev/null 2>&1; then
        echo "⚠️  Process still running, force killing..."
        kill -9 $PID
        sleep 1
    fi
    
    echo "✅ Backend stopped"
else
    echo "ℹ️  No backend process found"
fi

echo "🚀 Starting backend..."
python -m src.main > /dev/null 2>&1 &

sleep 2

# Check if it started
if ps aux | grep "python.*src.main" | grep -v grep > /dev/null; then
    echo "✅ Backend restarted successfully!"
    echo ""
    echo "📝 To view logs: tail -f logs/alphacent_*.log"
    echo "🛑 To stop: pkill -f 'python.*src.main'"
else
    echo "❌ Backend failed to start. Check logs for errors."
fi
