#!/bin/bash

# Test API with database integration

echo "Testing AlphaCent API with Database Integration"
echo "================================================"
echo ""

# First, login to get session cookie
echo "1. Logging in..."
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}' \
  -c cookies.txt \
  -s | python3 -m json.tool

echo ""
echo "2. Creating a strategy..."
STRATEGY_RESPONSE=$(curl -X POST "http://localhost:8000/strategies?mode=DEMO" \
  -H "Content-Type: application/json" \
  -b cookies.txt \
  -s \
  -d '{
    "name": "My First Database Strategy",
    "description": "Testing database persistence",
    "rules": {"indicator": "RSI", "threshold": 70},
    "symbols": ["AAPL", "MSFT", "GOOGL"],
    "risk_params": {
      "max_position_size_pct": 0.1,
      "stop_loss_pct": 0.02,
      "take_profit_pct": 0.04
    }
  }')

echo "$STRATEGY_RESPONSE" | python3 -m json.tool
STRATEGY_ID=$(echo "$STRATEGY_RESPONSE" | python3 -c "import sys, json; print(json.load(sys.stdin)['strategy_id'])")

echo ""
echo "3. Retrieving all strategies..."
curl -X GET "http://localhost:8000/strategies?mode=DEMO" \
  -b cookies.txt \
  -s | python3 -m json.tool

echo ""
echo "4. Retrieving specific strategy ($STRATEGY_ID)..."
curl -X GET "http://localhost:8000/strategies/$STRATEGY_ID?mode=DEMO" \
  -b cookies.txt \
  -s | python3 -m json.tool

echo ""
echo "================================================"
echo "✓ API Database Integration Test Complete!"
echo ""
echo "Now restart the server and run this script again to verify persistence!"
