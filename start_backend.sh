#!/bin/bash
# Start the AlphaCent backend server

# Activate virtual environment
source venv/bin/activate

# Start uvicorn server
echo "Starting AlphaCent backend on http://localhost:8000"
python -m uvicorn src.api.app:app --host 0.0.0.0 --port 8000
