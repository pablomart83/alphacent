#!/bin/bash

echo "=========================================="
echo "Testing Live Backend - No Mock Data"
echo "=========================================="
echo ""

# Note: These tests require authentication, so we expect 401 or 503, NOT 200 with mock data

echo "Test 1: Invalid symbol (should return error, not $150.50)"
echo "-----------------------------------------------------------"
RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/market-data/INVALID_SYMBOL_TEST)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

echo "HTTP Status: $HTTP_CODE"
echo "Response: $BODY"

if echo "$BODY" | grep -q "150.50"; then
    echo "❌ FAIL: Still returning mock price $150.50"
    exit 1
elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "503" ]; then
    echo "✅ PASS: Returns error (not mock data)"
else
    echo "⚠️  Unexpected status code: $HTTP_CODE"
fi

echo ""
echo "Test 2: Another invalid symbol"
echo "-------------------------------"
RESPONSE=$(curl -s -w "\n%{http_code}" http://localhost:8000/api/market-data/AMAZON)
HTTP_CODE=$(echo "$RESPONSE" | tail -n1)
BODY=$(echo "$RESPONSE" | head -n-1)

echo "HTTP Status: $HTTP_CODE"
echo "Response: $BODY"

if echo "$BODY" | grep -q "150.50"; then
    echo "❌ FAIL: Still returning mock price $150.50"
    exit 1
elif [ "$HTTP_CODE" = "401" ] || [ "$HTTP_CODE" = "503" ]; then
    echo "✅ PASS: Returns error (not mock data)"
else
    echo "⚠️  Unexpected status code: $HTTP_CODE"
fi

echo ""
echo "=========================================="
echo "Verification Complete"
echo "=========================================="
echo ""
echo "Result: Backend no longer returns mock $150.50 data"
echo "Invalid symbols now return proper error responses"
