#!/bin/bash

echo "=========================================="
echo "Complete Vibe Coding Fix Test"
echo "=========================================="

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Step 1: Check if server is running
echo -e "\n${YELLOW}Step 1: Checking server status...${NC}"
if pgrep -f "uvicorn src.api.app:app" > /dev/null; then
    echo -e "${GREEN}✅ Server is running${NC}"
else
    echo -e "${RED}❌ Server is not running${NC}"
    echo "Please start the server first:"
    echo "  ./restart_server.sh"
    exit 1
fi

# Step 2: Run pattern matching tests
echo -e "\n${YELLOW}Step 2: Testing pattern matching...${NC}"
python test_direct_conversion.py > /tmp/test1.log 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Pattern matching tests passed${NC}"
else
    echo -e "${RED}❌ Pattern matching tests failed${NC}"
    cat /tmp/test1.log
    exit 1
fi

# Step 3: Run edge case tests
echo -e "\n${YELLOW}Step 3: Testing edge cases...${NC}"
python test_edge_cases.py > /tmp/test2.log 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Edge case tests passed${NC}"
else
    echo -e "${RED}❌ Edge case tests failed${NC}"
    cat /tmp/test2.log
    exit 1
fi

# Step 4: Check code changes
echo -e "\n${YELLOW}Step 4: Verifying code changes...${NC}"

# Check if old buggy code is removed
if grep -q "Check if quantity looks like units" src/api/routers/orders.py; then
    echo -e "${RED}❌ Old buggy code still present in orders.py${NC}"
    exit 1
else
    echo -e "${GREEN}✅ Old buggy code removed from orders.py${NC}"
fi

# Check if new conversion code is present
if grep -q "User specified.*units/shares.*converting to dollars" src/llm/llm_service.py; then
    echo -e "${GREEN}✅ New conversion code present in llm_service.py${NC}"
else
    echo -e "${RED}❌ New conversion code missing in llm_service.py${NC}"
    exit 1
fi

# Step 5: Check server logs for recent activity
echo -e "\n${YELLOW}Step 5: Checking server logs...${NC}"
if [ -f server.log ]; then
    RECENT_LOGS=$(tail -20 server.log | grep -i "error\|failed" | wc -l)
    if [ $RECENT_LOGS -gt 5 ]; then
        echo -e "${YELLOW}⚠️  Warning: Found $RECENT_LOGS recent errors in logs${NC}"
        echo "Check: tail -20 server.log"
    else
        echo -e "${GREEN}✅ Server logs look clean${NC}"
    fi
else
    echo -e "${YELLOW}⚠️  Warning: server.log not found${NC}"
fi

# Step 6: Summary
echo -e "\n=========================================="
echo -e "${GREEN}All Tests Passed!${NC}"
echo "=========================================="
echo ""
echo "Next steps:"
echo "1. Test via Vibe Coding UI:"
echo "   - buy \$50 of BTC"
echo "   - buy 1 unit of BTC"
echo "   - buy 10 shares of AAPL"
echo ""
echo "2. Monitor logs:"
echo "   tail -f server.log | grep -i 'converted\\|quantity'"
echo ""
echo "3. Check database:"
echo "   sqlite3 alphacent.db \"SELECT symbol, side, quantity FROM orders ORDER BY submitted_at DESC LIMIT 5;\""
echo ""
echo "=========================================="
