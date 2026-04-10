#!/bin/bash

echo "Generating strategy with reasoning..."
echo "This may take 30-60 seconds as the LLM generates the strategy..."
echo ""

curl -X POST "http://localhost:8000/api/strategies/generate" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer demo_token" \
  -d '{
    "prompt": "Create a momentum strategy that buys stocks showing strong upward price trends over 20 days with high volume confirmation and sells when momentum weakens",
    "constraints": {
      "symbols": ["AAPL", "GOOGL", "MSFT"],
      "timeframe": "1d",
      "risk_tolerance": "medium"
    }
  }' \
  --max-time 120 \
  -w "\n\nHTTP Status: %{http_code}\n" \
  | python3 -m json.tool

echo ""
echo "✓ Strategy generated!"
echo "🌐 View in UI: http://localhost:5173"
echo "   1. Navigate to Strategies page"
echo "   2. Find the newly generated strategy"
echo "   3. Click 'View Reasoning' button to see the StrategyReasoningPanel"
