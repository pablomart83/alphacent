#!/bin/bash
# Backend Health Check Script
# Tests critical endpoints to verify backend is working

set -e

BASE_URL="http://localhost:8000"
COOKIE_FILE="/tmp/alphacent_cookies.txt"

echo "🔍 AlphaCent Backend Health Check"
echo "=================================="
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counter
PASSED=0
FAILED=0

test_endpoint() {
    local name=$1
    local method=$2
    local endpoint=$3
    local expected_code=$4
    local extra_args=$5
    
    echo -n "Testing $name... "
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" $extra_args "$BASE_URL$endpoint")
    elif [ "$method" = "POST" ]; then
        response=$(curl -s -w "\n%{http_code}" -X POST $extra_args "$BASE_URL$endpoint")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | head -n-1)
    
    if [ "$http_code" = "$expected_code" ]; then
        echo -e "${GREEN}✓ PASS${NC} (HTTP $http_code)"
        ((PASSED++))
        return 0
    else
        echo -e "${RED}✗ FAIL${NC} (Expected $expected_code, got $http_code)"
        echo "  Response: $body"
        ((FAILED++))
        return 1
    fi
}

# 1. Check if server is running
echo "1. Server Health Checks"
echo "----------------------"
test_endpoint "Root endpoint" "GET" "/" "200"
test_endpoint "Health check" "GET" "/health" "200"
echo ""

# 2. Test authentication
echo "2. Authentication Tests"
echo "----------------------"

# Login with correct credentials
echo -n "Testing login (valid credentials)... "
response=$(curl -s -w "\n%{http_code}" -X POST \
    -H "Content-Type: application/json" \
    -d '{"username":"admin","password":"admin123"}' \
    -c "$COOKIE_FILE" \
    "$BASE_URL/auth/login")

http_code=$(echo "$response" | tail -n1)
body=$(echo "$response" | head -n-1)

if [ "$http_code" = "200" ] && echo "$body" | grep -q "success"; then
    echo -e "${GREEN}✓ PASS${NC} (HTTP $http_code)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Expected 200 with success, got $http_code)"
    echo "  Response: $body"
    ((FAILED++))
fi

# Check auth status with session
test_endpoint "Auth status (with session)" "GET" "/auth/status" "200" "-b $COOKIE_FILE"

# Try accessing protected endpoint without session
test_endpoint "Protected endpoint (no session)" "GET" "/account" "401"

# Try accessing protected endpoint with session
test_endpoint "Protected endpoint (with session)" "GET" "/account?mode=DEMO" "200" "-b $COOKIE_FILE"

echo ""

# 3. Test CORS preflight
echo "3. CORS Tests"
echo "-------------"
echo -n "Testing OPTIONS request (CORS preflight)... "
response=$(curl -s -w "\n%{http_code}" -X OPTIONS \
    -H "Origin: http://localhost:5173" \
    -H "Access-Control-Request-Method: POST" \
    -H "Access-Control-Request-Headers: Content-Type" \
    "$BASE_URL/config/credentials")

http_code=$(echo "$response" | tail -n1)

if [ "$http_code" = "200" ] || [ "$http_code" = "204" ]; then
    echo -e "${GREEN}✓ PASS${NC} (HTTP $http_code)"
    ((PASSED++))
else
    echo -e "${RED}✗ FAIL${NC} (Expected 200/204, got $http_code)"
    ((FAILED++))
fi

echo ""

# 4. Test key endpoints
echo "4. API Endpoint Tests"
echo "--------------------"
test_endpoint "System status" "GET" "/control/system/status" "200" "-b $COOKIE_FILE"
test_endpoint "Services status" "GET" "/control/services" "200" "-b $COOKIE_FILE"
test_endpoint "Strategies list" "GET" "/strategies?mode=DEMO" "200" "-b $COOKIE_FILE"
test_endpoint "Orders list" "GET" "/orders?mode=DEMO" "200" "-b $COOKIE_FILE"
test_endpoint "Positions list" "GET" "/account/positions?mode=DEMO" "200" "-b $COOKIE_FILE"

echo ""

# Summary
echo "=================================="
echo "Test Summary"
echo "=================================="
echo -e "Passed: ${GREEN}$PASSED${NC}"
echo -e "Failed: ${RED}$FAILED${NC}"
echo ""

# Cleanup
rm -f "$COOKIE_FILE"

if [ $FAILED -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed! Backend is ready for testing.${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed. Please check the backend.${NC}"
    exit 1
fi
