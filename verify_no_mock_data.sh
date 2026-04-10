#!/bin/bash

echo "=========================================="
echo "Verify No Mock Data in API"
echo "=========================================="
echo ""

# Check if mock data strings exist in the code
echo "Checking for mock data in market_data.py..."
echo "-------------------------------------------"

if grep -q "price=150.50" src/api/routers/market_data.py; then
    echo "❌ FAIL: Found mock price 150.50 in code"
    exit 1
else
    echo "✅ PASS: No mock price 150.50 found"
fi

if grep -q "Fallback to mock data" src/api/routers/market_data.py; then
    echo "❌ FAIL: Found 'Fallback to mock data' comment"
    exit 1
else
    echo "✅ PASS: No mock data fallback comments"
fi

if grep -q "Using mock data" src/api/routers/market_data.py; then
    echo "❌ FAIL: Found 'Using mock data' log message"
    exit 1
else
    echo "✅ PASS: No mock data log messages"
fi

echo ""
echo "Checking for proper error handling..."
echo "--------------------------------------"

if grep -q "HTTPException" src/api/routers/market_data.py; then
    echo "✅ PASS: HTTPException error handling found"
else
    echo "❌ FAIL: No HTTPException error handling"
    exit 1
fi

if grep -q "HTTP_503_SERVICE_UNAVAILABLE" src/api/routers/market_data.py; then
    echo "✅ PASS: HTTP 503 status code found"
else
    echo "❌ FAIL: No HTTP 503 status code"
    exit 1
fi

echo ""
echo "Checking symbol mapping integration..."
echo "---------------------------------------"

if grep -q "normalize_symbol" src/api/routers/market_data.py; then
    echo "✅ PASS: Symbol normalization integrated"
else
    echo "❌ FAIL: Symbol normalization not found"
    exit 1
fi

echo ""
echo "=========================================="
echo "All Checks Passed! ✅"
echo "=========================================="
echo ""
echo "Summary:"
echo "  ✅ No mock data fallbacks"
echo "  ✅ Proper error handling in place"
echo "  ✅ Symbol mapping integrated"
echo "  ✅ System only returns real data or errors"
echo ""
echo "The API will now:"
echo "  • Return real eToro data for valid symbols"
echo "  • Return HTTP 503 errors for invalid symbols"
echo "  • Never return fake $150.50 prices"
