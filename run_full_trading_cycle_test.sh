#!/bin/bash

# Full Trading Cycle Test Runner
# This script runs the real trading test and logs all output

LOG_FILE="test_full_trading_cycle_$(date +%Y%m%d_%H%M%S).log"

echo "=========================================="
echo "FULL TRADING CYCLE TEST - REAL TRADES"
echo "=========================================="
echo ""
echo "⚠️  WARNING: This test will place REAL trades"
echo "⚠️  Make sure you have:"
echo "   1. eToro API credentials configured"
echo "   2. Sufficient balance in your account"
echo "   3. Reviewed the strategy parameters"
echo ""
echo "Log file: $LOG_FILE"
echo ""
read -p "Press ENTER to continue or Ctrl+C to cancel..."

echo ""
echo "🚀 Starting test..."
echo ""

# Run the test with tee to capture output
python test_full_trading_cycle_v1_2year.py 2>&1 | tee "$LOG_FILE"

EXIT_CODE=${PIPESTATUS[0]}

echo ""
echo "=========================================="
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ TEST PASSED"
else
    echo "❌ TEST FAILED (exit code: $EXIT_CODE)"
fi
echo "=========================================="
echo ""
echo "Full log saved to: $LOG_FILE"
echo ""

exit $EXIT_CODE
