# Task 21.16: Testing Guide

## Quick Start Testing

### Prerequisites
1. Backend service running on `localhost:8000`
2. Frontend running on `localhost:3000`
3. User logged in to the application

## Test Scenarios

### 1. Trading Mode Context (5 minutes)

#### Test 1.1: Initial Load
1. Open browser DevTools Console
2. Navigate to `http://localhost:3000`
3. Login to the application
4. **Expected:** Console shows "Fetching trading mode from backend"
5. **Expected:** No errors in console
6. Navigate to Portfolio page
7. **Expected:** Trading mode is consistent across pages

#### Test 1.2: Mode Change Propagation
1. Navigate to Settings page
2. Note current trading mode (DEMO or LIVE)
3. Click the other mode button
4. **Expected:** Success message appears
5. Navigate to Portfolio page
6. **Expected:** Same trading mode is active
7. Navigate to Market page
8. **Expected:** Same trading mode is active
9. Refresh browser
10. **Expected:** Trading mode persists after refresh

### 2. Position Actions (10 minutes)

#### Test 2.1: Modify Stop Loss
1. Navigate to Portfolio page
2. Ensure you have at least one open position
3. Click "SL" button on any position
4. **Expected:** Modal appears with "Modify Stop Loss" title
5. **Expected:** Input field is auto-focused
6. Enter a valid price (e.g., "100.50")
7. Click "Confirm"
8. **Expected:** Modal closes
9. **Expected:** Success alert appears
10. **Expected:** Position list refreshes

#### Test 2.2: Modify Take Profit
1. Navigate to Portfolio page
2. Click "TP" button on any position
3. **Expected:** Modal appears with "Modify Take Profit" title
4. Enter a valid price (e.g., "150.75")
5. Click "Confirm"
6. **Expected:** Modal closes
7. **Expected:** Success alert appears
8. **Expected:** Position list refreshes

#### Test 2.3: Close Position
1. Navigate to Portfolio page
2. Click "Close" button on any position
3. **Expected:** Browser confirmation dialog appears
4. Click "OK" to confirm
5. **Expected:** Button shows "Closing..." text
6. **Expected:** Position is removed from list after close
7. **Expected:** Total P&L updates

#### Test 2.4: Input Validation
1. Click "SL" button on any position
2. Leave input empty and click "Confirm"
3. **Expected:** Nothing happens (button should be disabled)
4. Enter "0" and click "Confirm"
5. **Expected:** Alert shows "Please enter a valid price"
6. Enter "-50" and click "Confirm"
7. **Expected:** Alert shows "Please enter a valid price"
8. Enter "abc" and click "Confirm"
9. **Expected:** Alert shows "Please enter a valid price"

#### Test 2.5: Modal Cancel
1. Click "SL" button on any position
2. Enter a price
3. Click "Cancel"
4. **Expected:** Modal closes without making changes
5. **Expected:** No API call made

#### Test 2.6: Button States
1. Click "SL" button on any position
2. **Expected:** All action buttons on all positions are disabled
3. Click "Cancel"
4. **Expected:** All action buttons are enabled again

### 3. Smart Portfolio Actions (10 minutes)

#### Test 3.1: Invest Action
1. Navigate to Market page
2. Scroll to Smart Portfolios section
3. Click "Invest" button on any portfolio
4. **Expected:** Modal appears with "Invest in Smart Portfolio" title
5. **Expected:** Minimum investment amount is displayed
6. Enter an amount (e.g., "1000")
7. Click "Confirm"
8. **Expected:** Button shows "Processing..." text
9. **Expected:** Modal closes after completion
10. **Expected:** Success alert appears

#### Test 3.2: Divest Action
1. Navigate to Market page
2. Click "Divest" button on any portfolio
3. **Expected:** Modal appears with "Divest from Smart Portfolio" title
4. Enter an amount (e.g., "500")
5. Click "Confirm"
6. **Expected:** Button shows "Processing..." text
7. **Expected:** Modal closes after completion
8. **Expected:** Success alert appears

#### Test 3.3: Input Validation
1. Click "Invest" button on any portfolio
2. Leave input empty and click "Confirm"
3. **Expected:** Nothing happens (button should be disabled)
4. Enter "0" and click "Confirm"
5. **Expected:** Alert shows "Please enter a valid amount"
6. Enter "-100" and click "Confirm"
7. **Expected:** Alert shows "Please enter a valid amount"

#### Test 3.4: Button States During Action
1. Click "Invest" button on any portfolio
2. Enter an amount
3. Click "Confirm"
4. **Expected:** All portfolio action buttons are disabled
5. **Expected:** Modal buttons are disabled
6. Wait for completion
7. **Expected:** All buttons are enabled again

### 4. Error Handling (5 minutes)

#### Test 4.1: Backend Unavailable
1. Stop the backend service
2. Navigate to Portfolio page
3. Click "SL" button on any position
4. Enter a price and click "Confirm"
5. **Expected:** Error alert appears with meaningful message
6. **Expected:** Modal remains open
7. Click "Cancel" to close modal

#### Test 4.2: Invalid API Response
1. Restart backend service
2. Navigate to Market page
3. Click "Invest" button
4. Enter an amount below minimum investment
5. Click "Confirm"
6. **Expected:** Error alert appears explaining the issue

### 5. Loading States (3 minutes)

#### Test 5.1: Position Close Loading
1. Navigate to Portfolio page
2. Click "Close" button
3. Confirm in dialog
4. **Expected:** Button text changes to "Closing..."
5. **Expected:** Button is disabled
6. **Expected:** Other action buttons on same row are disabled

#### Test 5.2: Modal Loading
1. Navigate to Market page
2. Click "Invest" button
3. Enter amount and click "Confirm"
4. **Expected:** Confirm button shows "Processing..."
5. **Expected:** Confirm button is disabled
6. **Expected:** Cancel button is disabled

### 6. Cross-Page Consistency (3 minutes)

#### Test 6.1: Trading Mode Consistency
1. Open browser in two tabs
2. Navigate to Portfolio in tab 1
3. Navigate to Market in tab 2
4. In tab 1, note the trading mode
5. In tab 2, verify same trading mode
6. Navigate to Settings in tab 1
7. Change trading mode
8. Navigate to Market in tab 1
9. **Expected:** New trading mode is active
10. Refresh tab 2
11. **Expected:** New trading mode is active in tab 2

## Expected API Calls

### Position Actions
- **Modify Stop Loss:** `PUT /account/positions/:id/stop-loss?mode=DEMO`
- **Modify Take Profit:** `PUT /account/positions/:id/take-profit?mode=DEMO`
- **Close Position:** `DELETE /account/positions/:id?mode=DEMO`

### Smart Portfolio Actions
- **Invest:** `POST /market-data/smart-portfolios/:id/invest`
- **Divest:** `POST /market-data/smart-portfolios/:id/divest`

### Config
- **Get Config:** `GET /config` (on app load)
- **Update Config:** `PUT /config` (when changing trading mode)

## Common Issues and Solutions

### Issue: Trading mode not loading
**Solution:** Check browser console for errors. Verify backend `/config` endpoint is working.

### Issue: Modal not appearing
**Solution:** Check for z-index conflicts. Verify no JavaScript errors in console.

### Issue: Actions not working
**Solution:** 
1. Check Network tab in DevTools for API calls
2. Verify backend endpoints are implemented
3. Check for CORS issues
4. Verify authentication token is valid

### Issue: Trading mode not persisting
**Solution:** 
1. Verify backend saves config to database
2. Check `/config` endpoint returns correct mode
3. Clear browser cache and retry

## Performance Checks

1. **Initial Load:** Should complete within 2 seconds
2. **Modal Open:** Should be instant (< 100ms)
3. **API Calls:** Should complete within 1 second
4. **Page Navigation:** Should be instant with context

## Browser Compatibility

Test in:
- [ ] Chrome (latest)
- [ ] Firefox (latest)
- [ ] Safari (latest)
- [ ] Edge (latest)

## Accessibility Checks

1. **Keyboard Navigation:**
   - [ ] Tab through all buttons
   - [ ] Enter key submits forms
   - [ ] Escape key closes modals (if implemented)

2. **Screen Reader:**
   - [ ] Button labels are descriptive
   - [ ] Modal titles are announced
   - [ ] Error messages are announced

## Sign-off

- [ ] All test scenarios pass
- [ ] No console errors
- [ ] No network errors
- [ ] Loading states work correctly
- [ ] Error handling works correctly
- [ ] Trading mode context works correctly
- [ ] All actions provide feedback

**Tested by:** _______________
**Date:** _______________
**Notes:** _______________
