#!/bin/bash

echo "================================================================================"
echo "SIMPLE AUTONOMOUS CYCLE TEST"
echo "================================================================================"

BACKEND_URL="http://localhost:8000"
COOKIE_FILE="/tmp/cycle_test_cookies.txt"

# 1. Check backend
echo ""
echo "[1/5] Checking backend..."
HEALTH=$(curl -s "$BACKEND_URL/health")
if [ $? -eq 0 ]; then
    echo "✓ Backend is running"
    echo "  Response: $HEALTH"
else
    echo "✗ Cannot connect to backend"
    exit 1
fi

# 2. Login to get session cookie
echo ""
echo "[2/5] Authenticating..."
LOGIN_RESPONSE=$(curl -s -c "$COOKIE_FILE" -X POST \
    -H "Content-Type: application/json" \
    -d '{"username": "admin", "password": "admin123"}' \
    "$BACKEND_URL/auth/login")

if echo "$LOGIN_RESPONSE" | grep -q '"success":true'; then
    echo "✓ Authenticated successfully"
else
    echo "⚠ Login failed, trying without auth..."
    echo "  Response: $LOGIN_RESPONSE"
fi

# 3. Get initial status
echo ""
echo "[3/5] Getting initial status..."
STATUS=$(curl -s -b "$COOKIE_FILE" "$BACKEND_URL/strategies/autonomous/status")
echo "  Status: $STATUS" | head -c 200
echo "..."

# 4. Get initial strategy count
echo ""
echo "[4/5] Getting initial strategy count..."
INITIAL_COUNT=$(sqlite3 alphacent.db "SELECT COUNT(*) FROM strategies WHERE created_at > datetime('now', '-1 hour')")
echo "  Strategies in last hour: $INITIAL_COUNT"

# 5. Trigger cycle
echo ""
echo "[5/5] Triggering cycle..."
echo "  This will take 15-30 minutes with 730 days of data..."
echo "  Started at: $(date)"
echo ""

START_TIME=$(date +%s)

RESULT=$(curl -s -b "$COOKIE_FILE" -X POST \
    -H "Content-Type: application/json" \
    -d '{"force": true}' \
    --max-time 3600 \
    "$BACKEND_URL/strategies/autonomous/trigger")

END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))

echo ""
echo "  Completed at: $(date)"
echo "  Duration: ${DURATION}s ($((DURATION / 60)) minutes)"
echo ""
echo "  Response: $RESULT"

# 5. Check results
echo ""
echo "================================================================================"
echo "CHECKING RESULTS"
echo "================================================================================"

sleep 2

FINAL_COUNT=$(sqlite3 alphacent.db "SELECT COUNT(*) FROM strategies WHERE created_at > datetime('now', '-1 hour')")
NEW_STRATEGIES=$((FINAL_COUNT - INITIAL_COUNT))

echo "Initial count: $INITIAL_COUNT"
echo "Final count: $FINAL_COUNT"
echo "New strategies: $NEW_STRATEGIES"

echo ""
echo "Recent strategies:"
sqlite3 alphacent.db "SELECT name, symbols, status, created_at FROM strategies WHERE created_at > datetime('now', '-1 hour') ORDER BY created_at DESC LIMIT 10"

echo ""
echo "================================================================================"
echo "SUMMARY"
echo "================================================================================"
echo "Cycle duration: ${DURATION}s ($((DURATION / 60)) minutes)"
echo "Strategies created: $NEW_STRATEGIES"

if [ $NEW_STRATEGIES -lt 10 ]; then
    echo ""
    echo "⚠ WARNING: Only $NEW_STRATEGIES strategies created!"
    echo "  Expected: 30-50 with proposal_count=50"
    echo ""
    echo "  Check backend terminal for logs showing:"
    echo "  - 'Proposing 50 strategies'"
    echo "  - 'Generated X strategies from templates'"
    echo "  - 'Walk-forward validation: X/Y strategies passed'"
    exit 1
else
    echo ""
    echo "✓ SUCCESS: $NEW_STRATEGIES strategies created"
    exit 0
fi
